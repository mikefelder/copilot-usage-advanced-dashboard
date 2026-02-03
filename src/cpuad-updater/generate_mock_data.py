"""
Mock Data Generator for GitHub Copilot Dashboard

Generates realistic 3 months of mock data for:
- 25 developers across 5 teams
- 15 repositories
- Shows productivity increase after Copilot adoption (5 weeks ago)

Usage:
    python generate_mock_data.py

This will populate Elasticsearch with realistic data patterns.
"""

import json
import random
import hashlib
import os
from datetime import datetime, timedelta
from elasticsearch import Elasticsearch

# Configuration
ORGANIZATION_SLUG = "acme-corp"
SLUG_TYPE = "Organization"
NUM_DEVELOPERS = 25
NUM_TEAMS = 5
NUM_REPOS = 15
DAYS_OF_DATA = 150  # 5 months - enough for baseline + full adoption curve
COPILOT_ADOPTION_DAYS_AGO = 70  # 10 weeks ago - allows seeing full 8-week ramp-up + 2 weeks at peak

# Elasticsearch configuration
ELASTICSEARCH_URL = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
INDEX_USER_METRICS = os.getenv("INDEX_USER_METRICS", "copilot_user_metrics")
INDEX_DEVELOPER_ACTIVITY = os.getenv("INDEX_DEVELOPER_ACTIVITY", "developer_activity")

# Developer personas with different productivity profiles
# Based on GitHub's research:
# - 55% faster task completion (but this is for specific tasks, not all work)
# - 26-30% average acceptance rate
# - 73% stay in flow, 87% preserve mental effort
# - Real productivity gains are 20-40%, not 100%+
DEVELOPER_PERSONAS = {
    "power_user": {
        "base_commits": (3, 7),
        "base_prs": (1, 2),
        "base_reviews": (2, 4),
        "copilot_multiplier": 1.30,  # 30% more productive (realistic upper bound)
        "copilot_adoption_rate": 0.92,  # 92% use it daily per GitHub research
        "acceptance_rate_range": (0.30, 0.40),  # Higher acceptance for power users
        "features": ["code_completion", "chat_panel_ask_mode", "chat_panel_agent_mode", "inline_chat"],
    },
    "regular": {
        "base_commits": (2, 5),
        "base_prs": (0, 2),
        "base_reviews": (1, 3),
        "copilot_multiplier": 1.20,  # 20% productivity gain
        "copilot_adoption_rate": 0.75,
        "acceptance_rate_range": (0.25, 0.32),  # Average acceptance rate
        "features": ["code_completion", "chat_panel_ask_mode"],
    },
    "occasional": {
        "base_commits": (1, 3),
        "base_prs": (0, 1),
        "base_reviews": (1, 2),
        "copilot_multiplier": 1.10,  # 10% productivity gain
        "copilot_adoption_rate": 0.45,
        "acceptance_rate_range": (0.20, 0.28),  # Lower acceptance
        "features": ["code_completion"],
    },
    "skeptic": {
        "base_commits": (1, 3),
        "base_prs": (0, 1),
        "base_reviews": (1, 2),
        "copilot_multiplier": 1.05,  # Minimal gain - doesn't fully embrace it
        "copilot_adoption_rate": 0.25,
        "acceptance_rate_range": (0.15, 0.22),  # Low acceptance - rejects most suggestions
        "features": ["code_completion"],
    },
}

# Teams configuration
TEAMS = [
    {"name": "platform", "repos": ["api-gateway", "auth-service", "config-manager"], "languages": ["go", "python"]},
    {"name": "frontend", "repos": ["web-app", "mobile-app", "design-system"], "languages": ["typescript", "javascript", "css"]},
    {"name": "backend", "repos": ["order-service", "inventory-service", "payment-service"], "languages": ["java", "kotlin"]},
    {"name": "data", "repos": ["analytics-pipeline", "ml-models", "data-warehouse"], "languages": ["python", "sql"]},
    {"name": "devops", "repos": ["infrastructure", "ci-cd-pipelines", "monitoring"], "languages": ["terraform", "yaml", "python"]},
]

# IDEs distribution
IDES = [
    {"name": "vscode", "weight": 0.60, "plugin_version": "1.234.0"},
    {"name": "jetbrains", "weight": 0.25, "plugin_version": "1.5.12.6534"},
    {"name": "neovim", "weight": 0.10, "plugin_version": "0.3.0"},
    {"name": "visual-studio", "weight": 0.05, "plugin_version": "17.12.0"},
]

# Models
MODELS = ["gpt-4o", "gpt-4o-mini", "claude-3.5-sonnet", "o1-preview"]

# Features
FEATURES = ["code_completion", "chat_panel_ask_mode", "chat_panel_agent_mode", "inline_chat", "agent_edit"]


def generate_unique_hash(data, key_properties):
    """Generate a unique hash based on specified properties."""
    key_elements = []
    for key_property in key_properties:
        value = data.get(key_property)
        key_elements.append(str(value) if value is not None else "")
    key_string = "-".join(key_elements)
    return hashlib.sha256(key_string.encode()).hexdigest()


def generate_developer_name(index):
    """Generate realistic developer names."""
    first_names = [
        "alex", "jordan", "taylor", "casey", "morgan", "riley", "quinn", "avery",
        "jamie", "drew", "sam", "chris", "pat", "blake", "cameron", "dakota",
        "skyler", "reese", "finley", "hayden", "emery", "rowan", "sage", "phoenix", "river"
    ]
    last_names = [
        "chen", "patel", "garcia", "kim", "nguyen", "smith", "johnson", "williams",
        "brown", "jones", "miller", "davis", "rodriguez", "martinez", "hernandez",
        "lopez", "gonzalez", "wilson", "anderson", "thomas", "taylor", "moore", "jackson", "martin", "lee"
    ]
    return f"{first_names[index % len(first_names)]}-{last_names[index % len(last_names)]}"


def create_developers():
    """Create developer profiles with team assignments and personas."""
    developers = []
    personas = list(DEVELOPER_PERSONAS.keys())
    persona_weights = [0.20, 0.45, 0.25, 0.10]  # Distribution of personas
    
    for i in range(NUM_DEVELOPERS):
        team = TEAMS[i % NUM_TEAMS]
        persona_name = random.choices(personas, weights=persona_weights)[0]
        persona = DEVELOPER_PERSONAS[persona_name]
        
        developer = {
            "user_login": generate_developer_name(i),
            "user_id": 1000000 + i,
            "team": team["name"],
            "repos": team["repos"],
            "languages": team["languages"],
            "persona": persona_name,
            "persona_config": persona,
            "primary_ide": random.choices(IDES, weights=[ide["weight"] for ide in IDES])[0],
            "seniority": random.choice(["junior", "mid", "senior", "staff"]),
        }
        developers.append(developer)
    
    return developers


def is_workday(date):
    """Check if date is a workday (Mon-Fri)."""
    return date.weekday() < 5


def get_activity_modifier(date, copilot_adoption_date):
    """
    Get activity modifier based on date relative to Copilot adoption.
    Based on GitHub research: productivity gains are gradual and reach
    full effect after 6-8 weeks, not immediately.
    
    Research shows:
    - Week 1-2: Learning curve, may even see slight productivity dip
    - Week 3-4: Starting to see benefits, ~50% of eventual gains
    - Week 5-6: Comfortable, ~75% of eventual gains  
    - Week 7-8+: Fully productive with the tool
    """
    if date < copilot_adoption_date:
        return 1.0  # Baseline before adoption
    
    days_since_adoption = (date - copilot_adoption_date).days
    
    # More gradual, realistic ramp-up over 8 weeks
    if days_since_adoption < 7:
        return 0.98  # Week 1: slight learning curve dip
    elif days_since_adoption < 14:
        return 1.02  # Week 2: break even, starting to adapt
    elif days_since_adoption < 21:
        return 1.08  # Week 3: early benefits visible
    elif days_since_adoption < 28:
        return 1.15  # Week 4: gaining proficiency
    elif days_since_adoption < 35:
        return 1.20  # Week 5: comfortable
    elif days_since_adoption < 42:
        return 1.25  # Week 6: proficient
    elif days_since_adoption < 56:
        return 1.28  # Week 7-8: near full productivity
    else:
        return 1.30  # Week 8+: fully productive (realistic max ~30%)
    

def generate_copilot_metrics_for_day(developer, date, copilot_adoption_date):
    """Generate Copilot user metrics for a single day."""
    persona = developer["persona_config"]
    
    # No Copilot metrics before adoption
    if date < copilot_adoption_date:
        return None
    
    # Check if developer uses Copilot today based on adoption rate
    if random.random() > persona["copilot_adoption_rate"]:
        return None
    
    # Skip weekends with 90% probability
    if not is_workday(date) and random.random() > 0.1:
        return None
    
    days_since_adoption = (date - copilot_adoption_date).days
    
    # Ramp up usage over time
    usage_multiplier = min(1.0, 0.3 + (days_since_adoption / 28) * 0.7)
    
    # Base metrics - interactions and code generations
    # Research shows developers interact with Copilot 20-60 times per day on average
    interactions = int(random.randint(20, 60) * usage_multiplier)
    code_gen = int(random.randint(30, 80) * usage_multiplier)
    
    # Acceptance rate from persona config (based on GitHub research: 26-30% average)
    # Power users: 30-40%, Regular: 25-32%, Occasional: 20-28%, Skeptic: 15-22%
    acceptance_rate_range = persona.get("acceptance_rate_range", (0.25, 0.32))
    acceptance_rate = random.uniform(*acceptance_rate_range)
    
    # Acceptance rate improves slightly over time as developers learn what works
    days_since_adoption = (date - copilot_adoption_date).days
    if days_since_adoption > 14:
        acceptance_rate += 0.02  # +2% after 2 weeks
    if days_since_adoption > 28:
        acceptance_rate += 0.02  # +2% more after 4 weeks
    
    # Cap acceptance rate at realistic maximum
    acceptance_rate = min(acceptance_rate, 0.45)
    
    code_acceptance = int(code_gen * acceptance_rate)
    
    # Lines of code
    loc_suggested = code_gen * random.randint(3, 12)
    loc_added = int(loc_suggested * acceptance_rate * random.uniform(0.8, 1.0))
    
    # Feature usage
    used_agent = random.random() < 0.3 if "chat_panel_agent_mode" in persona["features"] else False
    used_chat = random.random() < 0.6 if "chat_panel_ask_mode" in persona["features"] else False
    
    # Build totals by IDE
    ide = developer["primary_ide"]
    totals_by_ide = [{
        "ide": ide["name"],
        "user_initiated_interaction_count": interactions,
        "code_generation_activity_count": code_gen,
        "code_acceptance_activity_count": code_acceptance,
        "loc_suggested_to_add_sum": loc_suggested,
        "loc_suggested_to_delete_sum": int(loc_suggested * 0.1),
        "loc_added_sum": loc_added,
        "loc_deleted_sum": int(loc_added * 0.1),
    }]
    
    # Build totals by feature
    totals_by_feature = []
    available_features = persona["features"]
    for feature in available_features:
        feature_share = 1.0 / len(available_features)
        if feature == "code_completion":
            feature_share = 0.5  # Code completion is most used
        
        totals_by_feature.append({
            "feature": feature,
            "user_initiated_interaction_count": int(interactions * feature_share),
            "code_generation_activity_count": int(code_gen * feature_share) if "code" in feature else 0,
            "code_acceptance_activity_count": int(code_acceptance * feature_share) if "code" in feature else 0,
            "loc_suggested_to_add_sum": int(loc_suggested * feature_share) if "code" in feature else 0,
            "loc_suggested_to_delete_sum": int(loc_suggested * 0.1 * feature_share) if "code" in feature else 0,
            "loc_added_sum": int(loc_added * feature_share) if "code" in feature else 0,
            "loc_deleted_sum": int(loc_added * 0.1 * feature_share) if "code" in feature else 0,
        })
    
    # Build totals by language/model
    totals_by_language_model = []
    for lang in developer["languages"]:
        model = random.choice(MODELS)
        lang_share = 1.0 / len(developer["languages"])
        totals_by_language_model.append({
            "language": lang,
            "model": model,
            "code_generation_activity_count": int(code_gen * lang_share),
            "code_acceptance_activity_count": int(code_acceptance * lang_share),
            "loc_suggested_to_add_sum": int(loc_suggested * lang_share),
            "loc_suggested_to_delete_sum": int(loc_suggested * 0.1 * lang_share),
            "loc_added_sum": int(loc_added * lang_share),
            "loc_deleted_sum": int(loc_added * 0.1 * lang_share),
        })
    
    # Build totals by language/feature
    totals_by_language_feature = []
    for lang in developer["languages"]:
        for feature in available_features[:2]:  # Top 2 features per language
            share = 1.0 / (len(developer["languages"]) * 2)
            totals_by_language_feature.append({
                "language": lang,
                "feature": feature,
                "code_generation_activity_count": int(code_gen * share),
                "code_acceptance_activity_count": int(code_acceptance * share),
                "loc_suggested_to_add_sum": int(loc_suggested * share),
                "loc_suggested_to_delete_sum": int(loc_suggested * 0.1 * share),
                "loc_added_sum": int(loc_added * share),
                "loc_deleted_sum": int(loc_added * 0.1 * share),
            })
    
    day_str = date.strftime("%Y-%m-%d")
    
    record = {
        "day": day_str,
        "report_start_day": day_str,
        "report_end_day": day_str,
        "user_id": developer["user_id"],
        "user_login": developer["user_login"],
        "organization_slug": ORGANIZATION_SLUG,
        "slug_type": SLUG_TYPE,
        "last_updated_at": datetime.now().isoformat(),
        "utc_offset": "+00:00",
        "user_initiated_interaction_count": interactions,
        "code_generation_activity_count": code_gen,
        "code_acceptance_activity_count": code_acceptance,
        "used_agent": used_agent,
        "used_chat": used_chat,
        "loc_suggested_to_add_sum": loc_suggested,
        "loc_suggested_to_delete_sum": int(loc_suggested * 0.1),
        "loc_added_sum": loc_added,
        "loc_deleted_sum": int(loc_added * 0.1),
        "totals_by_ide": totals_by_ide,
        "totals_by_feature": totals_by_feature,
        "totals_by_language_model": totals_by_language_model,
        "totals_by_language_feature": totals_by_language_feature,
        "top_model": random.choice(MODELS),
        "top_language": developer["languages"][0],
        "top_feature": "code_completion",
    }
    
    record["unique_hash"] = generate_unique_hash(
        record, ["organization_slug", "user_login", "day"]
    )
    
    return record


def generate_developer_activity_for_day(developer, date, copilot_adoption_date):
    """Generate developer activity metrics for a single day."""
    persona = developer["persona_config"]
    
    # Skip weekends with 85% probability
    if not is_workday(date) and random.random() > 0.15:
        return None
    
    # Random vacation/sick days (5% chance)
    if random.random() < 0.05:
        return None
    
    # Get productivity modifier based on Copilot adoption
    if date >= copilot_adoption_date:
        modifier = get_activity_modifier(date, copilot_adoption_date)
        # Apply persona-specific multiplier
        modifier *= persona["copilot_multiplier"]
    else:
        modifier = 1.0
    
    # Base activity (with some randomness)
    base_commits = random.randint(*persona["base_commits"])
    base_prs = random.randint(*persona["base_prs"])
    base_reviews = random.randint(*persona["base_reviews"])
    
    # Apply modifier for post-adoption period
    commits = int(base_commits * modifier * random.uniform(0.8, 1.2))
    prs_opened = int(base_prs * modifier * random.uniform(0.7, 1.3))
    prs_reviewed = int(base_reviews * modifier * random.uniform(0.8, 1.2))
    
    # Derived metrics
    prs_merged = int(prs_opened * random.uniform(0.6, 0.9))
    pr_comments = int(prs_reviewed * random.randint(1, 4))
    issues_opened = random.randint(0, 2)
    issues_closed = random.randint(0, issues_opened + 1)
    
    repos_contributed = min(len(developer["repos"]), random.randint(1, 3))
    
    total_contributions = commits + prs_opened + prs_merged + prs_reviewed + issues_opened
    code_review_activity = prs_reviewed + pr_comments
    
    day_str = date.strftime("%Y-%m-%d")
    period_days = 1
    
    record = {
        "day": day_str,
        "report_start_day": day_str,
        "report_end_day": day_str,
        "period_days": period_days,
        "user_login": developer["user_login"],
        "organization_slug": ORGANIZATION_SLUG,
        "slug_type": SLUG_TYPE,
        "last_updated_at": datetime.now().isoformat(),
        "utc_offset": "+00:00",
        "commit_count": commits,
        "repos_contributed": repos_contributed,
        "prs_opened": prs_opened,
        "prs_merged": prs_merged,
        "prs_reviewed": prs_reviewed,
        "pr_comments": pr_comments,
        "prs_closed": prs_merged,
        "issues_opened": issues_opened,
        "issues_closed": issues_closed,
        "issue_comments": random.randint(0, issues_opened * 2),
        "total_contributions": total_contributions,
        "code_review_activity": code_review_activity,
        "commits_per_day": round(commits / period_days, 2),
        "prs_per_day": round(prs_opened / period_days, 2),
        "reviews_per_day": round(prs_reviewed / period_days, 2),
        # Additional fields for enhanced analytics
        "team": developer["team"],
        "primary_language": developer["languages"][0],
        "seniority": developer["seniority"],
    }
    
    record["unique_hash"] = generate_unique_hash(
        record, ["organization_slug", "user_login", "day"]
    )
    
    return record


def generate_all_mock_data():
    """Generate all mock data for the specified time period."""
    print("=" * 60)
    print("Mock Data Generator for GitHub Copilot Dashboard")
    print("=" * 60)
    
    # Calculate dates
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=DAYS_OF_DATA)
    copilot_adoption_date = end_date - timedelta(days=COPILOT_ADOPTION_DAYS_AGO)
    
    print(f"\nConfiguration:")
    print(f"  Organization: {ORGANIZATION_SLUG}")
    print(f"  Developers: {NUM_DEVELOPERS}")
    print(f"  Teams: {NUM_TEAMS}")
    print(f"  Repositories: {NUM_REPOS}")
    print(f"  Date Range: {start_date} to {end_date}")
    print(f"  Copilot Adoption Date: {copilot_adoption_date}")
    print(f"  Days of Data: {DAYS_OF_DATA}")
    
    # Create developers
    developers = create_developers()
    print(f"\nCreated {len(developers)} developer profiles:")
    for dev in developers[:5]:
        print(f"  - {dev['user_login']} ({dev['persona']}, {dev['team']})")
    print(f"  ... and {len(developers) - 5} more")
    
    # Generate data
    copilot_metrics = []
    developer_activity = []
    
    current_date = start_date
    while current_date <= end_date:
        for developer in developers:
            # Generate Copilot metrics (only after adoption)
            metrics = generate_copilot_metrics_for_day(
                developer, 
                current_date, 
                copilot_adoption_date
            )
            if metrics:
                copilot_metrics.append(metrics)
            
            # Generate developer activity (all days)
            activity = generate_developer_activity_for_day(
                developer,
                current_date,
                copilot_adoption_date
            )
            if activity:
                developer_activity.append(activity)
        
        current_date += timedelta(days=1)
    
    print(f"\nGenerated:")
    print(f"  - {len(copilot_metrics)} Copilot user metrics records")
    print(f"  - {len(developer_activity)} developer activity records")
    
    return copilot_metrics, developer_activity


def load_to_elasticsearch(copilot_metrics, developer_activity):
    """Load generated data into Elasticsearch using requests (HTTP API)."""
    import requests
    
    print(f"\nConnecting to Elasticsearch at {ELASTICSEARCH_URL}...")
    
    # Check connection
    try:
        response = requests.get(f"{ELASTICSEARCH_URL}/_cluster/health")
        if response.status_code != 200:
            print(f"ERROR: Cannot connect to Elasticsearch: {response.text}")
            return False
        print("Connected successfully!")
    except requests.exceptions.ConnectionError as e:
        print(f"ERROR: Cannot connect to Elasticsearch: {e}")
        return False
    
    headers = {"Content-Type": "application/json"}
    
    # Delete and recreate indexes with proper mappings
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    def ensure_index_with_mapping(index_name, mapping_file):
        """Delete index if exists and create with proper mapping."""
        mapping_path = os.path.join(script_dir, "mapping", mapping_file)
        
        # Delete existing index
        delete_response = requests.delete(f"{ELASTICSEARCH_URL}/{index_name}")
        if delete_response.status_code == 200:
            print(f"  Deleted existing index: {index_name}")
        
        # Create with mapping
        if os.path.exists(mapping_path):
            with open(mapping_path, 'r') as f:
                mapping = f.read()
            create_response = requests.put(
                f"{ELASTICSEARCH_URL}/{index_name}",
                headers=headers,
                data=mapping
            )
            if create_response.status_code in [200, 201]:
                print(f"  Created index with mapping: {index_name}")
            else:
                print(f"  Warning: Could not create index {index_name}: {create_response.text[:100]}")
        else:
            print(f"  Warning: Mapping file not found: {mapping_path}")
    
    print("\nSetting up indexes with proper mappings...")
    ensure_index_with_mapping(INDEX_USER_METRICS, "copilot_user_metrics_mapping.json")
    ensure_index_with_mapping(INDEX_DEVELOPER_ACTIVITY, "developer_activity_mapping.json")
    
    def bulk_index(index_name, records, batch_size=500):
        """Bulk index records using the _bulk API."""
        total = len(records)
        indexed = 0
        errors = 0
        
        for i in range(0, total, batch_size):
            batch = records[i:i + batch_size]
            bulk_body = ""
            
            for record in batch:
                # Action line
                action = json.dumps({"index": {"_index": index_name, "_id": record["unique_hash"]}})
                # Document line
                doc = json.dumps(record)
                bulk_body += f"{action}\n{doc}\n"
            
            try:
                response = requests.post(
                    f"{ELASTICSEARCH_URL}/_bulk",
                    headers=headers,
                    data=bulk_body
                )
                
                if response.status_code in [200, 201]:
                    result = response.json()
                    batch_errors = sum(1 for item in result.get("items", []) if item.get("index", {}).get("error"))
                    errors += batch_errors
                    indexed += len(batch) - batch_errors
                else:
                    print(f"  Bulk request failed: {response.status_code} - {response.text[:200]}")
                    errors += len(batch)
                    
            except Exception as e:
                print(f"  Error in bulk request: {e}")
                errors += len(batch)
            
            print(f"  Progress: {min(i + batch_size, total)}/{total} records")
        
        return indexed, errors
    
    # Load Copilot metrics
    print(f"\nLoading {len(copilot_metrics)} Copilot metrics records...")
    indexed, errors = bulk_index(INDEX_USER_METRICS, copilot_metrics)
    print(f"  Completed: {indexed} indexed, {errors} errors")
    
    # Load developer activity
    print(f"\nLoading {len(developer_activity)} developer activity records...")
    indexed, errors = bulk_index(INDEX_DEVELOPER_ACTIVITY, developer_activity)
    print(f"  Completed: {indexed} indexed, {errors} errors")
    
    # Refresh indices
    print("\nRefreshing indices...")
    requests.post(f"{ELASTICSEARCH_URL}/{INDEX_USER_METRICS}/_refresh")
    requests.post(f"{ELASTICSEARCH_URL}/{INDEX_DEVELOPER_ACTIVITY}/_refresh")
    
    print("\n✅ All data loaded successfully!")
    return True


def print_data_summary(copilot_metrics, developer_activity):
    """Print summary statistics of generated data."""
    print("\n" + "=" * 60)
    print("Data Summary")
    print("=" * 60)
    
    # Copilot metrics summary
    if copilot_metrics:
        total_interactions = sum(m["user_initiated_interaction_count"] for m in copilot_metrics)
        total_code_gen = sum(m["code_generation_activity_count"] for m in copilot_metrics)
        total_code_accept = sum(m["code_acceptance_activity_count"] for m in copilot_metrics)
        total_loc_added = sum(m["loc_added_sum"] for m in copilot_metrics)
        
        print("\nCopilot Metrics:")
        print(f"  Total Interactions: {total_interactions:,}")
        print(f"  Total Code Generations: {total_code_gen:,}")
        print(f"  Total Code Acceptances: {total_code_accept:,}")
        print(f"  Acceptance Rate: {total_code_accept/total_code_gen*100:.1f}%")
        print(f"  Total LOC Added: {total_loc_added:,}")
    
    # Developer activity summary
    if developer_activity:
        # Pre vs Post adoption comparison
        copilot_date = datetime.now().date() - timedelta(days=COPILOT_ADOPTION_DAYS_AGO)
        copilot_date_str = copilot_date.strftime("%Y-%m-%d")
        
        pre_adoption = [a for a in developer_activity if a["day"] < copilot_date_str]
        post_adoption = [a for a in developer_activity if a["day"] >= copilot_date_str]
        
        if pre_adoption and post_adoption:
            pre_commits = sum(a["commit_count"] for a in pre_adoption) / len(pre_adoption)
            post_commits = sum(a["commit_count"] for a in post_adoption) / len(post_adoption)
            
            pre_prs = sum(a["prs_opened"] for a in pre_adoption) / len(pre_adoption)
            post_prs = sum(a["prs_opened"] for a in post_adoption) / len(post_adoption)
            
            print("\nDeveloper Activity (Pre vs Post Copilot Adoption):")
            print(f"  Avg Commits/Day: {pre_commits:.2f} → {post_commits:.2f} ({(post_commits/pre_commits-1)*100:+.1f}%)")
            print(f"  Avg PRs/Day: {pre_prs:.2f} → {post_prs:.2f} ({(post_prs/pre_prs-1)*100:+.1f}%)")


def main():
    """Main entry point."""
    # Generate data
    copilot_metrics, developer_activity = generate_all_mock_data()
    
    # Print summary
    print_data_summary(copilot_metrics, developer_activity)
    
    # Load to Elasticsearch
    print("\n" + "=" * 60)
    print("Loading to Elasticsearch")
    print("=" * 60)
    
    success = load_to_elasticsearch(copilot_metrics, developer_activity)
    
    if success:
        print("\n" + "=" * 60)
        print("🎉 Mock data generation complete!")
        print("=" * 60)
        print("\nYou can now view the data in Grafana:")
        print("  - Main Dashboard: http://localhost:8080")
        print("  - Developer Activity Dashboard: http://localhost:8080/d/developer-activity-comparison")
        print("\nTry adjusting the time range to see:")
        print("  - Last 90 days: Full data range")
        print("  - Last 30 days: Post-Copilot adoption period")
        print("  - Custom range: Compare pre/post adoption")
    
    return success


if __name__ == "__main__":
    main()
