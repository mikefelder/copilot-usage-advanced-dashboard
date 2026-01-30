"""
Developer Activity Metrics Fetcher

Fetches developer activity metrics from GitHub API to allow comparison
with GitHub Copilot usage metrics. This includes:
- Commits
- Pull Requests (opened, merged, reviewed)
- Code Reviews
- Issues (opened, closed)

These metrics can be visualized alongside Copilot metrics to understand
the relationship between Copilot usage and overall developer productivity.
"""

import json
import requests
import os
import hashlib
from datetime import datetime, timedelta
from log_utils import configure_logger, current_time
from zoneinfo import ZoneInfo

logger = configure_logger(log_path=os.getenv("LOG_PATH", "logs"))


def get_utc_offset():
    """Get the UTC offset string for the configured timezone."""
    tz_name = os.environ.get("TZ", "GMT")
    try:
        local_tz = ZoneInfo(tz_name)
    except Exception:
        local_tz = ZoneInfo("GMT")
    now = datetime.now(local_tz)
    offset_sec = now.utcoffset().total_seconds()
    offset_hours = int(offset_sec // 3600)
    offset_minutes = int((offset_sec % 3600) // 60)
    offset_str = f"{offset_hours:+03}:{abs(offset_minutes):02}"
    return offset_str


def generate_unique_hash(data, key_properties):
    """Generate a unique hash based on specified properties."""
    key_elements = []
    for key_property in key_properties:
        value = data.get(key_property)
        key_elements.append(str(value) if value is not None else "")
    key_string = "-".join(key_elements)
    return hashlib.sha256(key_string.encode()).hexdigest()


class DeveloperActivityFetcher:
    """
    Fetches developer activity metrics from GitHub API.
    
    This class retrieves various metrics about developer activity that can
    be compared with Copilot usage metrics to understand productivity patterns.
    """

    def __init__(self, token, organization_slug, is_standalone=False):
        self.token = token
        self.organization_slug = organization_slug
        self.is_standalone = is_standalone
        self.slug_type = "Standalone" if is_standalone else "Organization"
        self.api_type = "enterprises" if is_standalone else "orgs"
        self.headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self.graphql_url = "https://api.github.com/graphql"
        self.utc_offset = get_utc_offset()
        logger.info(f"Initialized DeveloperActivityFetcher for {self.slug_type}: {organization_slug}")

    def _make_rest_request(self, url, error_return_value=None):
        """Make a REST API request to GitHub."""
        if error_return_value is None:
            error_return_value = []
        
        logger.info(f"REST API request: {url}")
        try:
            response = requests.get(url, headers=self.headers)
            logger.info(f"Response status code: {response.status_code}")
            
            if response.status_code != 200:
                logger.error(f"HTTP {response.status_code} error: {response.text}")
                return error_return_value
            
            return response.json()
        except Exception as e:
            logger.error(f"Request failed: {e}")
            return error_return_value

    def _make_graphql_request(self, query, variables=None):
        """Make a GraphQL request to GitHub."""
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        
        try:
            response = requests.post(self.graphql_url, json=payload, headers=self.headers)
            if response.status_code == 200:
                data = response.json()
                if "errors" in data:
                    logger.error(f"GraphQL errors: {data['errors']}")
                    return None
                return data.get("data")
            else:
                logger.error(f"GraphQL request failed: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"GraphQL request error: {e}")
            return None

    def get_organization_members(self):
        """Get all members of the organization."""
        members = []
        page = 1
        per_page = 100
        
        while True:
            url = f"https://api.github.com/{self.api_type}/{self.organization_slug}/members?page={page}&per_page={per_page}"
            page_members = self._make_rest_request(url, [])
            
            if not page_members:
                break
            
            members.extend([m.get("login") for m in page_members if m.get("login")])
            
            if len(page_members) < per_page:
                break
            page += 1
        
        logger.info(f"Found {len(members)} organization members")
        return members

    def get_organization_repos(self):
        """Get all repositories in the organization."""
        repos = []
        page = 1
        per_page = 100
        
        while True:
            url = f"https://api.github.com/{self.api_type}/{self.organization_slug}/repos?page={page}&per_page={per_page}&type=all"
            page_repos = self._make_rest_request(url, [])
            
            if not page_repos:
                break
            
            repos.extend([r.get("name") for r in page_repos if r.get("name")])
            
            if len(page_repos) < per_page:
                break
            page += 1
        
        logger.info(f"Found {len(repos)} repositories")
        return repos

    def get_user_commits(self, user_login, since_date, until_date, repos=None):
        """
        Get commit activity for a user across organization repositories.
        
        Uses the search API to find commits by author within the date range.
        """
        if repos is None:
            repos = self.get_organization_repos()
        
        total_commits = 0
        additions = 0
        deletions = 0
        repos_contributed = set()
        
        # Use search API for commits by this author in the org
        since_str = since_date.strftime("%Y-%m-%d")
        until_str = until_date.strftime("%Y-%m-%d")
        
        query = f"org:{self.organization_slug} author:{user_login} author-date:{since_str}..{until_str}"
        url = f"https://api.github.com/search/commits?q={query}&per_page=100"
        
        headers = self.headers.copy()
        headers["Accept"] = "application/vnd.github.cloak-preview+json"
        
        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                total_commits = data.get("total_count", 0)
                
                # Get details from items
                for item in data.get("items", []):
                    repo_name = item.get("repository", {}).get("name")
                    if repo_name:
                        repos_contributed.add(repo_name)
            else:
                logger.warning(f"Commit search failed for {user_login}: {response.status_code}")
        except Exception as e:
            logger.error(f"Error fetching commits for {user_login}: {e}")
        
        return {
            "commit_count": total_commits,
            "repos_contributed": len(repos_contributed),
            "repos_list": list(repos_contributed)
        }

    def get_user_pull_requests(self, user_login, since_date, until_date):
        """
        Get pull request activity for a user.
        
        Returns counts of PRs created, merged, and reviewed.
        """
        since_str = since_date.strftime("%Y-%m-%d")
        until_str = until_date.strftime("%Y-%m-%d")
        
        metrics = {
            "prs_opened": 0,
            "prs_merged": 0,
            "prs_reviewed": 0,
            "pr_comments": 0,
            "prs_closed": 0
        }
        
        # PRs opened by user
        query = f"org:{self.organization_slug} author:{user_login} created:{since_str}..{until_str} is:pr"
        url = f"https://api.github.com/search/issues?q={query}&per_page=1"
        data = self._make_rest_request(url, {})
        metrics["prs_opened"] = data.get("total_count", 0)
        
        # PRs merged by user (authored and merged)
        query = f"org:{self.organization_slug} author:{user_login} merged:{since_str}..{until_str} is:pr"
        url = f"https://api.github.com/search/issues?q={query}&per_page=1"
        data = self._make_rest_request(url, {})
        metrics["prs_merged"] = data.get("total_count", 0)
        
        # PRs reviewed by user (using reviewed-by)
        query = f"org:{self.organization_slug} reviewed-by:{user_login} created:{since_str}..{until_str} is:pr"
        url = f"https://api.github.com/search/issues?q={query}&per_page=1"
        data = self._make_rest_request(url, {})
        metrics["prs_reviewed"] = data.get("total_count", 0)
        
        # PRs where user commented
        query = f"org:{self.organization_slug} commenter:{user_login} created:{since_str}..{until_str} is:pr"
        url = f"https://api.github.com/search/issues?q={query}&per_page=1"
        data = self._make_rest_request(url, {})
        metrics["pr_comments"] = data.get("total_count", 0)
        
        return metrics

    def get_user_issues(self, user_login, since_date, until_date):
        """
        Get issue activity for a user.
        
        Returns counts of issues created, closed, and commented on.
        """
        since_str = since_date.strftime("%Y-%m-%d")
        until_str = until_date.strftime("%Y-%m-%d")
        
        metrics = {
            "issues_opened": 0,
            "issues_closed": 0,
            "issue_comments": 0
        }
        
        # Issues opened by user
        query = f"org:{self.organization_slug} author:{user_login} created:{since_str}..{until_str} is:issue"
        url = f"https://api.github.com/search/issues?q={query}&per_page=1"
        data = self._make_rest_request(url, {})
        metrics["issues_opened"] = data.get("total_count", 0)
        
        # Issues closed by user
        query = f"org:{self.organization_slug} author:{user_login} closed:{since_str}..{until_str} is:issue"
        url = f"https://api.github.com/search/issues?q={query}&per_page=1"
        data = self._make_rest_request(url, {})
        metrics["issues_closed"] = data.get("total_count", 0)
        
        # Issues where user commented
        query = f"org:{self.organization_slug} commenter:{user_login} created:{since_str}..{until_str} is:issue"
        url = f"https://api.github.com/search/issues?q={query}&per_page=1"
        data = self._make_rest_request(url, {})
        metrics["issue_comments"] = data.get("total_count", 0)
        
        return metrics

    def fetch_developer_activity_for_members(self, members=None, days_back=28, save_to_json=True):
        """
        Fetch comprehensive developer activity metrics for all organization members.
        
        Args:
            members: Optional list of member logins. If None, fetches all org members.
            days_back: Number of days to look back for activity (default: 28 to match Copilot metrics)
            save_to_json: Whether to save results to JSON file
            
        Returns:
            List of developer activity records, one per user per day
        """
        if members is None:
            members = self.get_organization_members()
        
        if not members:
            logger.warning("No members found for developer activity fetching")
            return []
        
        # Calculate date range
        until_date = datetime.now()
        since_date = until_date - timedelta(days=days_back)
        
        logger.info(f"Fetching developer activity for {len(members)} members from {since_date.date()} to {until_date.date()}")
        
        all_records = []
        current_time_str = current_time()
        
        for member in members:
            logger.info(f"Fetching activity for member: {member}")
            
            try:
                # Get all metrics for this user
                commit_metrics = self.get_user_commits(member, since_date, until_date)
                pr_metrics = self.get_user_pull_requests(member, since_date, until_date)
                issue_metrics = self.get_user_issues(member, since_date, until_date)
                
                # Calculate aggregate scores
                total_contributions = (
                    commit_metrics.get("commit_count", 0) +
                    pr_metrics.get("prs_opened", 0) +
                    pr_metrics.get("prs_merged", 0) +
                    pr_metrics.get("prs_reviewed", 0) +
                    issue_metrics.get("issues_opened", 0)
                )
                
                code_review_activity = (
                    pr_metrics.get("prs_reviewed", 0) +
                    pr_metrics.get("pr_comments", 0)
                )
                
                # Create record for this user (aggregated for the period)
                record = {
                    "user_login": member,
                    "organization_slug": self.organization_slug,
                    "slug_type": self.slug_type,
                    "day": until_date.strftime("%Y-%m-%d"),
                    "report_start_day": since_date.strftime("%Y-%m-%d"),
                    "report_end_day": until_date.strftime("%Y-%m-%d"),
                    "period_days": days_back,
                    
                    # Commit metrics
                    "commit_count": commit_metrics.get("commit_count", 0),
                    "repos_contributed": commit_metrics.get("repos_contributed", 0),
                    
                    # PR metrics
                    "prs_opened": pr_metrics.get("prs_opened", 0),
                    "prs_merged": pr_metrics.get("prs_merged", 0),
                    "prs_reviewed": pr_metrics.get("prs_reviewed", 0),
                    "pr_comments": pr_metrics.get("pr_comments", 0),
                    "prs_closed": pr_metrics.get("prs_closed", 0),
                    
                    # Issue metrics  
                    "issues_opened": issue_metrics.get("issues_opened", 0),
                    "issues_closed": issue_metrics.get("issues_closed", 0),
                    "issue_comments": issue_metrics.get("issue_comments", 0),
                    
                    # Aggregate metrics
                    "total_contributions": total_contributions,
                    "code_review_activity": code_review_activity,
                    
                    # Calculated rates (per day)
                    "commits_per_day": round(commit_metrics.get("commit_count", 0) / days_back, 2),
                    "prs_per_day": round(pr_metrics.get("prs_opened", 0) / days_back, 2),
                    "reviews_per_day": round(pr_metrics.get("prs_reviewed", 0) / days_back, 2),
                    
                    # Metadata
                    "last_updated_at": current_time_str,
                    "utc_offset": self.utc_offset,
                }
                
                # Generate unique hash
                record["unique_hash"] = generate_unique_hash(
                    record,
                    key_properties=["organization_slug", "user_login", "report_start_day", "report_end_day"]
                )
                
                all_records.append(record)
                logger.info(f"Processed activity for {member}: {total_contributions} total contributions")
                
            except Exception as e:
                logger.error(f"Error fetching activity for {member}: {e}")
                continue
        
        # Save to JSON if requested
        if save_to_json and all_records:
            from main import dict_save_to_json_file
            dict_save_to_json_file(
                all_records,
                f"{self.organization_slug}_developer_activity"
            )
        
        logger.info(f"Fetched developer activity for {len(all_records)} members")
        return all_records


def fetch_developer_activity(token, organization_slug, is_standalone=False, days_back=28):
    """
    Convenience function to fetch developer activity metrics.
    
    Args:
        token: GitHub PAT token
        organization_slug: Organization/enterprise slug
        is_standalone: Whether this is a standalone enterprise
        days_back: Number of days to look back
        
    Returns:
        List of developer activity records
    """
    fetcher = DeveloperActivityFetcher(token, organization_slug, is_standalone)
    return fetcher.fetch_developer_activity_for_members(days_back=days_back)


if __name__ == "__main__":
    # Test the fetcher
    import os
    
    token = os.getenv("GITHUB_PAT")
    org = os.getenv("ORGANIZATION_SLUGS", "").split(",")[0].strip()
    
    if not token or not org:
        print("Set GITHUB_PAT and ORGANIZATION_SLUGS environment variables")
        exit(1)
    
    is_standalone = org.startswith("standalone:")
    org = org.replace("standalone:", "")
    
    records = fetch_developer_activity(token, org, is_standalone, days_back=28)
    print(f"Fetched {len(records)} developer activity records")
    
    if records:
        print(json.dumps(records[0], indent=2))
