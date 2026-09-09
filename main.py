import os
import re
import pandas as pd
from jobspy import scrape_jobs
from datetime import datetime

# ==============================================================================
# 1. SUCHKRITERIEN, BRANCHEN & REGIONEN
# ==============================================================================
# Rollen
JOB_ROLES = ["Produktmanager", "Projektmanager", "Product Manager", "Project Manager"]

# Gezielte Abfrage von Energieversorgern im DACH-Raum
ENERGY_COMPANIES = [
    "Tiwag", "Salzburg AG", "Illwerke vkw", "Stadtwerke Kufstein", 
    "Innsbrucker Kommunalbetriebe", "IKB", "Axpo", "CKW", "EKZ", "SWM"
]

# Alle Suchbegriffe kombinieren
SEARCH_TERMS = JOB_ROLES + ENERGY_COMPANIES

ENERGY_KEYWORDS = [
    "energie", "energy", "strom", "gas", "photovoltaik", "pv", "solar", 
    "wind", "erneuerbar", "renewable", "kraftwerk", "grid", "netz", "stadtwerke",
    "wasserstoff", "fernwärme", "tiwag", "salzburg ag", "axpo", "illwerke"
]

# Regionen-Konfiguration mit strengen Whitelists
REGION_CONFIG = {
    "AT": {
        "flag": "🇦🇹",
        "name": "Österreich (Tirol/Vorarlberg/Salzburg)",
        "locations": [
            # Vorarlberg & Bodensee
            "Vorarlberg", "Bregenz", "Dornbirn", "Feldkirch", "Bludenz", "Lustenau", "Hard", "Götzis",
            # Tirol
            "Tirol", "Innsbruck", "Kufstein", "Schwaz", "Imst", "Kitzbühel", "Lienz", "Reutte", "Hall",
            # Salzburger Land (NEU)
            "Salzburg", "Hallein", "Bischofshofen", "Zell am See", "St. Johann", "Saalfelden", "Seekirchen"
        ],
        "min_salary": 78000,
        "currency": "EUR"
    },
    "DE": {
        "flag": "🇩🇪",
        "name": "Deutschland (Dresden +50km)",
        "locations": [
            "Dresden", "Radebeul", "Meißen", "Freiberg", "Pirna", "Bautzen", 
            "Coswig", "Riesa", "Freital", "Heidenau", "Kamenz", "Großenhain"
        ],
        "min_salary": 78000,
        "currency": "EUR"
    },
    "CH": {
        "flag": "🇨🇭",
        "name": "Schweiz (Raum Zürich)",
        "locations": [
            "Zürich", "Zurich", "Winterthur", "Kloten", "Dietikon", "Uster", "Wetzikon"
        ],
        "min_salary": 115000,
        "currency": "CHF"
    },
    "LI": {
        "flag": "🇱🇮",
        "name": "Liechtenstein",
        "locations": [
            "Liechtenstein", "Vaduz", "Schaan", "Triesen", "Balzers", "Eschen", "Mauren"
        ],
        "min_salary": 115000,
        "currency": "CHF"
    }
}

# Schwarze Liste: Orte, die wir NICHT im Dashboard sehen wollen
EXCLUDED_LOCATIONS = ["wien", "vienna", "graz", "linz", "münchen", "berlin", "hamburg"]

# ==============================================================================
# 2. FILTER & LOGIK
# ==============================================================================
def parse_salary_from_text(text):
    if not isinstance(text, str):
        return None
    matches = re.findall(
        r'(?:€|EUR|CHF)\s*(\d{2,3}[\.\',]?\d{3})|(\d{2,3}[\.\',]?\d{3})\s*(?:€|EUR|CHF)', 
        text, 
        re.IGNORECASE
    )
    found_salaries = []
    for match in matches:
        val_str = match[0] or match[1]
        if val_str:
            clean_val = int(val_str.replace('.', '').replace("'", '').replace(',', ''))
            if clean_val > 10000:
                found_salaries.append(clean_val)
    return max(found_salaries) if found_salaries else None

def check_region_and_salary(location, description, job_min_amount):
    loc_lower = str(location).lower()
    
    # 1. Hater Ausschluss für unerwünschte Großstädte (Wien etc.)
    if any(ex_loc in loc_lower for ex_loc in EXCLUDED_LOCATIONS):
        return False, None, None, None

    matched_country = None
    matched_config = None
    
    # 2. Exakte Prüfung gegen erlaubte Regionen
    for country, config in REGION_CONFIG.items():
        if any(allowed_loc.lower() in loc_lower for allowed_loc in config["locations"]):
            matched_country = country
            matched_config = config
            break
            
    # Falls der Ort in KEINER definierten Zielregion liegt -> Verwerfen
    if not matched_country:
        return False, None, None, None

    parsed_salary = parse_salary_from_text(description)
    salary = parsed_salary or (int(job_min_amount) if pd.notnull(job_min_amount) else None)
        
    required_min = matched_config["min_salary"]
    currency = matched_config["currency"]

    if salary and isinstance(salary, int) and salary < required_min:
        return False, None, None, None

    salary_str = f"{salary:,} {currency}".replace(',', '.') if salary else f"Nicht angegeben (Ziel: ≥{required_min:,} {currency})".replace(',', '.')
    return True, matched_country, salary_str, currency

def is_energy_sector(title, description, company):
    full_text = f"{title} {description} {company}".lower()
    return any(kw in full_text for kw in ENERGY_KEYWORDS)

def fetch_and_filter_jobs():
    search_locations = ["Austria", "Germany", "Switzerland", "Liechtenstein"]
    all_results = []
    
    for term in SEARCH_TERMS:
        for loc in search_locations:
            print(f"Suche nach '{term}' in {loc}...")
            try:
                jobs = scrape_jobs(
                    site_name=["linkedin", "indeed", "glassdoor"],
                    search_term=term,
                    location=loc,
                    results_wanted=15,
                    hours_old=48
                )
                all_results.append(jobs)
            except Exception as e:
                print(f"Fehler bei {term} in {loc}: {e}")

    if not all_results:
        return pd.DataFrame()

    combined_df = pd.concat(all_results, ignore_index=True)
    combined_df.drop_duplicates(subset=['title', 'company'], inplace=True)
    
    processed = []
    for _, row in combined_df.iterrows():
        title = str(row.get('title', ''))
        location = str(row.get('location', ''))
        description = str(row.get('description', ''))
        company = str(row.get('company', 'N/A'))
        
        valid_region, country, salary_display, currency = check_region_and_salary(
            location, description, row.get('min_amount')
        )
        
        if not valid_region:
            continue

        is_energy = is_energy_sector(title, description, company)

        processed.append({
            "title": title,
            "company": company,
            "country_code": country,
            "country_flag": REGION_CONFIG[country]["flag"],
            "location": location,
            "salary": salary_display,
            "is_energy": is_energy,
            "site": str(row.get('site')).capitalize(),
            "url": row.get('job_url')
        })

    result_df = pd.DataFrame(processed)
    if not result_df.empty:
        result_df.sort_values(by=["is_energy"], ascending=False, inplace=True)
        
    return result_df

# ==============================================================================
# 3. HTML DASHBOARD GENERIERUNG
# ==============================================================================
def generate_html(jobs_df):
    now = datetime.now().strftime("%d.%m.%Y um %H:%M Uhr")
    
    html = f"""<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Job Dashboard | PM & PM</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background-color: #f8f9fa; margin: 0; padding: 15px; color: #212529; }}
        .container {{ max-width: 800px; margin: 0 auto; background: #ffffff; padding: 20px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }}
        h1 {{ margin-top: 0; font-size: 22px; color: #111; border-bottom: 2px solid #e9ecef; padding-bottom: 10px; }}
        .meta-info {{ font-size: 13px; color: #6c757d; margin-bottom: 20px; }}
        .job-card {{ border: 1px solid #e9ecef; border-radius: 8px; padding: 15px; margin-bottom: 12px; background: #fff; position: relative; transition: border-color 0.2s; }}
        .job-card.energy {{ border-left: 5px solid #ffc107; background: #fffdf5; }}
        .job-title {{ font-size: 16px; font-weight: 700; color: #0d6efd; text-decoration: none; display: block; margin-bottom: 6px; }}
        .job-title:hover {{ text-decoration: underline; }}
        .company {{ font-weight: 600; color: #333; }}
        .details {{ font-size: 13px; color: #495057; margin-top: 6px; }}
        .badge-container {{ margin-top: 10px; display: flex; gap: 6px; flex-wrap: wrap; }}
        .badge {{ font-size: 11px; font-weight: 600; padding: 3px 8px; border-radius: 4px; background: #e9ecef; color: #495057; }}
        .badge-energy {{ background: #fff3cd; color: #856404; border: 1px solid #ffeeba; }}
        .badge-country {{ background: #e2e3e5; color: #383d41; }}
        .no-jobs {{ text-align: center; padding: 40px; color: #6c757d; font-size: 15px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🎯 Job Dashboard: Produkt- & Projektmanager</h1>
        <div class="meta-info">Fokus-Regionen: 🇦🇹 Tirol/Vorarlberg/Salzburg | 🇩🇪 Dresden+50km | 🇨🇭 Zürich | 🇱🇮 Liechtenstein &nbsp;•&nbsp; Stand: <b>{now}</b></div>
    """

    if jobs_df.empty:
        html += '<div class="no-jobs">Keine passenden Stellenangebote in deinen definierten Zielregionen gefunden.</div>'
    else:
        for _, row in jobs_df.iterrows():
            energy_badge = '<span class="badge badge-energy">⚡ Energiebranche / Versorger</span>' if row['is_energy'] else ''
            card_class = "job-card energy" if row['is_energy'] else "job-card"
            
            html += f"""
            <div class="{card_class}">
                <a href="{row['url']}" target="_blank" class="job-title">{row['title']}</a>
                <div class="details">🏢 <span class="company">{row['company']}</span> &nbsp;|&nbsp; 📍 {row['location']}</div>
                <div class="details">💰 <b>Gehalt:</b> {row['salary']}</div>
                <div class="badge-container">
                    <span class="badge badge-country">{row['country_flag']} {row['country_code']}</span>
                    <span class="badge">{row['site']}</span>
                    {energy_badge}
                </div>
            </div>
            """

    html += """
    </div>
</body>
</html>
"""
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

if __name__ == "__main__":
    jobs = fetch_and_filter_jobs()
    generate_html(jobs)
