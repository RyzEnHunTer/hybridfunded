import sys
import json
import re
import urllib.request
import os

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

PRESETS_FILE = os.path.join(os.path.dirname(__file__), "prop_firm_presets.json")

def scrape_url(url):
    print(f"Scraping {url}...")
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            html = response.read().decode('utf-8')
            
        if BeautifulSoup:
            soup = BeautifulSoup(html, 'html.parser')
            text = soup.get_text(separator=' ')
        else:
            print("[Warning] BeautifulSoup not installed, using raw HTML. Run 'pip install beautifulsoup4' for better results.")
            text = html
        return text
    except Exception as e:
        print(f"Failed to scrape URL: {e}")
        return ""

def parse_rules(text):
    print("Parsing extracted text for rules...")
    
    # Very basic regex heuristics
    daily_dd = re.search(r"(?i)(?:daily loss|daily drawdown).*?(\d+(?:\.\d+)?)%", text)
    max_dd = re.search(r"(?i)(?:max loss|maximum drawdown).*?(\d+(?:\.\d+)?)%", text)
    target = re.search(r"(?i)(?:profit target).*?(\d+(?:\.\d+)?)%", text)
    
    parsed_data = {
        "CHALLENGE": {
            "daily_dd_pct": float(daily_dd.group(1)) if daily_dd else None,
            "max_dd_pct": float(max_dd.group(1)) if max_dd else None,
            "profit_target_pct": float(target.group(1)) if target else None,
            "news_trading_allowed": True,
            "weekend_holding_allowed": True,
            "news_profit_cap_pct": None,
            "consistency_rule_pct": None
        },
        "LIVE": {
            "daily_dd_pct": float(daily_dd.group(1)) if daily_dd else None,
            "max_dd_pct": float(max_dd.group(1)) if max_dd else None,
            "profit_target_pct": None, # Live usually has no target
            "news_trading_allowed": True,
            "weekend_holding_allowed": True,
            "news_profit_cap_pct": None,
            "consistency_rule_pct": None
        }
    }
    return parsed_data

def add_to_presets(firm_name, rules_dict):
    if not os.path.exists(PRESETS_FILE):
        data = {}
    else:
        with open(PRESETS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            
    data[firm_name] = rules_dict
    
    with open(PRESETS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
        
    print(f"Successfully added {firm_name} to {PRESETS_FILE}!")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python prop_rule_scraper.py <FIRM_NAME> <URL>")
        sys.exit(1)
        
    firm_name = sys.argv[1].upper().replace(" ", "_")
    url = sys.argv[2]
    
    text = scrape_url(url)
    if text:
        rules = parse_rules(text)
        print(f"Extracted Rules for {firm_name}:")
        print(json.dumps(rules, indent=4))
        
        # In a real tool, we might ask for user confirmation here
        add_to_presets(firm_name, rules)
