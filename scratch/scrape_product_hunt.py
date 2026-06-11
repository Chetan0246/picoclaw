import urllib.request
import re
import html

url = "https://www.producthunt.com/"
req = urllib.request.Request(
    url,
    headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"
    }
)
try:
    print("Fetching Product Hunt homepage...")
    with urllib.request.urlopen(req, timeout=15) as response:
        html_content = response.read().decode("utf-8", errors="ignore")
        
    print(f"Successfully fetched {len(html_content)} bytes of HTML.")
    
    # 1. Find all product slugs
    # Format: href="/products/slug"
    product_slugs = re.findall(r'href=[\'"]/products/([^\'"]+)[\'"]', html_content)
    unique_slugs = []
    for slug in product_slugs:
        slug = slug.split("?")[0]
        if slug not in unique_slugs:
            unique_slugs.append(slug)
            
    print(f"Found {len(unique_slugs)} unique product slugs. Extracting details...")
    
    products = []
    for slug in unique_slugs:
        # Search for title and tagline context near each slug
        # We search in a local substring range around each slug occurrence to avoid global matching mistakes
        matches = [m.start() for m in re.finditer(rf'/products/{re.escape(slug)}', html_content)]
        if not matches:
            continue
            
        pos = matches[0]
        # Slice 1500 chars after the match
        slice_text = html_content[pos:pos+1500]
        
        # Parse title
        # Match: href="/products/slug">TITLE</a> or with absolute span inside
        # E.g. /products/slug"><span class="..."></span>Title</a>
        title = "Unknown"
        title_m = re.search(r'^[^>]*?>\s*(?:<span[^>]*></span>\s*)?(.*?)\s*</a>', slice_text, re.DOTALL)
        if title_m:
            title = re.sub(r'<[^>]+>', '', title_m.group(1)).strip()
            title = html.unescape(title)
            
        # Parse tagline
        # Sibling span tag with class containing 'text-secondary'
        tagline = "No tagline available"
        tagline_m = re.search(r'<span[^>]*class="[^"]*text-secondary[^"]*"[^>]*>(.*?)</span>', slice_text, re.DOTALL)
        if tagline_m:
            tagline = re.sub(r'<[^>]+>', '', tagline_m.group(1)).strip()
            tagline = html.unescape(tagline)
            
        # Skip icon-only links or UI fragments (where title is empty or matches navigation elements)
        if title in ["Unknown", "Icon/Image Link", ""] or len(title) > 80:
            continue
            
        products.append({
            "slug": slug,
            "title": title,
            "tagline": tagline,
            "url": f"https://www.producthunt.com/products/{slug}"
        })
        
    print(f"\nSuccessfully parsed {len(products)} products from the homepage:\n")
    
    # Save results as a Markdown file
    md_output = [
        "# Product Hunt Scraped Products of the Day\n",
        f"Scraped on: 2026-06-11\n",
        "| # | Product Name | Tagline | Link |",
        "|---|---|---|---|"
    ]
    for idx, p in enumerate(products):
        name_link = f"[{p['title']}]({p['url']})"
        md_output.append(f"| {idx+1} | {name_link} | {p['tagline']} | [View]({p['url']}) |")
        print(f"[{idx+1}] {p['title']}")
        print(f"    Tagline: {p['tagline']}")
        print(f"    URL:     {p['url']}\n")
        
    # Write to a file
    with open("scratch/product_hunt_daily.md", "w", encoding="utf-8") as f:
        f.write("\n".join(md_output))
        
    print("Saved Markdown report to scratch/product_hunt_daily.md.")
    
except Exception as e:
    print(f"Error scraping Product Hunt: {e}")
