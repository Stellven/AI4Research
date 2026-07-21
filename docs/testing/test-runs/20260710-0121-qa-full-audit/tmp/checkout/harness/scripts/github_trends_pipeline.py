import os
import sys
import json
import time
import logging
import requests
from datetime import datetime, timedelta, timezone

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load .env file manually if exists
env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                k, v = line.strip().split('=', 1)
                os.environ[k] = v

class GitHubTrendsPipeline:
    def __init__(self, github_token=None, local_llm_url="http://localhost:8000/v1", cloud_llm_api_key=None, cloud_llm_base_url="https://api.openai.com/v1"):
        self.github_token = github_token or os.environ.get("GITHUB_TOKEN")
        self.local_llm_url = local_llm_url
        self.cloud_llm_api_key = cloud_llm_api_key or os.environ.get("OPENAI_API_KEY")
        self.cloud_llm_base_url = cloud_llm_base_url

        self.headers = {"Accept": "application/vnd.github.v3+json"}
        if self.github_token:
            self.headers["Authorization"] = f"token {self.github_token}"

        # Data storage paths
        self.data_dir = os.path.join(os.path.dirname(__file__), "../data/github_trends")
        os.makedirs(self.data_dir, exist_ok=True)
        self.db_path = os.path.join(self.data_dir, "repo_master.json")
        self.snapshots_dir = os.path.join(self.data_dir, "snapshots")
        os.makedirs(self.snapshots_dir, exist_ok=True)

        self.repo_master = self._load_repo_master()

    def _load_repo_master(self):
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading repo master: {e}")
        return {}

    def _save_repo_master(self):
        with open(self.db_path, "w") as f:
            json.dump(self.repo_master, f, indent=2)

    def _load_snapshot(self, repo_id, date_str):
        safe_id = repo_id.replace("/", "_")
        path = os.path.join(self.snapshots_dir, f"{safe_id}_{date_str}.json")
        if os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f)
        return None

    def _save_snapshot(self, repo_data, date_str):
        safe_id = repo_data['repo_id'].replace("/", "_")
        path = os.path.join(self.snapshots_dir, f"{safe_id}_{date_str}.json")
        with open(path, "w") as f:
            json.dump(repo_data, f, indent=2)

    # ---------------------------------------------------------
    # 1. Discovery
    # ---------------------------------------------------------
    def discover_repos(self):
        """
        根据 Topic (ai-agent, mcp 等) 和 Trending 列表发现项目
        """
        logger.info("Starting project discovery via GitHub API...")
        discovered_repos = set()
        topics = ["ai-agent", "mcp", "inference-compute"]

        for topic in topics:
            url = f"https://api.github.com/search/repositories?q=topic:{topic}&sort=stars&order=desc"
            try:
                resp = requests.get(url, headers=self.headers, timeout=10)
                if resp.status_code == 200:
                    items = resp.json().get("items", [])
                    for item in items[:20]: # Top 20 per topic for daily scan
                        discovered_repos.add(item["full_name"])
            except Exception as e:
                logger.error(f"Failed to fetch topic {topic}: {e}")

        # Also ensure tracking standard ones
        discovered_repos.add("ChromeDevTools/chrome-devtools-mcp")
        discovered_repos.add("anthropics/claude-plugins-official")

        return list(discovered_repos)

    # ---------------------------------------------------------
    # 2. Snapshot & Metrics
    # ---------------------------------------------------------
    def fetch_repo_data(self, repo_full_name):
        logger.info(f"Fetching GitHub data for {repo_full_name}...")
        url = f"https://api.github.com/repos/{repo_full_name}"
        try:
            resp = requests.get(url, headers=self.headers, timeout=10)
            if resp.status_code != 200:
                logger.warning(f"Failed to fetch repo info {repo_full_name}: HTTP {resp.status_code}")
                return None

            data = resp.json()

            # Try to get README snippet
            readme_url = f"https://api.github.com/repos/{repo_full_name}/readme"
            readme_content = ""
            readme_resp = requests.get(readme_url, headers={"Accept": "application/vnd.github.v3.raw", **self.headers}, timeout=10)
            if readme_resp.status_code == 200:
                readme_content = readme_resp.text[:5000] # get first 5000 chars

            return {
                "repo_id": repo_full_name,
                "stars": data.get("stargazers_count", 0),
                "forks": data.get("forks_count", 0),
                "open_issues": data.get("open_issues_count", 0),
                "description": data.get("description", ""),
                "language": data.get("language", ""),
                "readme": readme_content,
                "updated_at": data.get("updated_at"),
                "snapshot_time": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            logger.error(f"Error fetching repo data for {repo_full_name}: {e}")
            return None

    def detect_sudden_hot(self, repo_data):
        repo_id = repo_data['repo_id']
        current_stars = repo_data['stars']

        # Load past snapshots
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        yesterday_str = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        last_week_str = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")

        self._save_snapshot(repo_data, today_str)

        if repo_id not in self.repo_master:
            self.repo_master[repo_id] = {
                "first_seen_at": datetime.now(timezone.utc).isoformat(),
                "tracking_status": "active"
            }
            self._save_repo_master()

        y_snapshot = self._load_snapshot(repo_id, yesterday_str)
        w_snapshot = self._load_snapshot(repo_id, last_week_str)

        stars_y = y_snapshot["stars"] if y_snapshot else current_stars
        stars_w = w_snapshot["stars"] if w_snapshot else current_stars

        stars_delta_24h = current_stars - stars_y
        stars_delta_7d = current_stars - stars_w
        avg_7d = stars_delta_7d / 7.0 if stars_delta_7d > 0 else 0

        logger.info(f"[{repo_id}] Stars: {current_stars}, 24h_delta: {stars_delta_24h}, 7d_avg: {avg_7d:.2f}")

        # PRD Detector: Sudden Hot Detector
        # stars_delta_24h >= max(50, avg_7d*3)
        threshold = max(50, avg_7d * 3)
        if stars_delta_24h >= threshold:
            logger.info(f"🔥 Sudden Hot detected for {repo_id}! Delta={stars_delta_24h} >= {threshold}")
            return True

        # Optional: mock condition for newly discovered repos to pass through if we don't have history yet
        if not y_snapshot and current_stars > 50:
            logger.info(f"✨ New potential project {repo_id} without history. Passing for analysis.")
            return True

        return False

    # ---------------------------------------------------------
    # 3. Intelligence Pipeline
    # ---------------------------------------------------------
    def extract_evidence_local(self, repo_data):
        logger.info(f"Extracting evidence for {repo_data['repo_id']} using local LLM...")

        prompt = (
            f"Analyze the following GitHub repository and extract key 'evidence atoms' (e.g., technical breakthroughs, "
            f"important releases, mentioned trending terms like MCP/Agents).\n\n"
            f"Repo: {repo_data['repo_id']}\n"
            f"Description: {repo_data['description']}\n"
            f"README snippet: {repo_data['readme'][:2000]}\n\n"
            f"Return a JSON array of string evidence atoms."
        )

        try:
            # Assuming an OpenAI-compatible local endpoint
            resp = requests.post(
                f"{self.local_llm_url}/chat/completions",
                json={
                    "model": "qwen", # or thunderomlx
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1
                },
                timeout=30
            )
            if resp.status_code == 200:
                content = resp.json()['choices'][0]['message']['content']
                # basic parsing
                return {"evidence_atoms": [content.strip()]}
        except Exception as e:
            logger.warning(f"Local LLM call failed, using fallback: {e}")

        return {
            "evidence_atoms": ["Fallback evidence: Active community and solid documentation."]
        }

    def generate_analysis_card(self, repo_data, evidence):
        logger.info(f"Generating insight card for {repo_data['repo_id']} using cloud LLM...")

        prompt = f"""
        You are an AI Influence Analyst. Analyze this project and generate an intelligence card.
        Repo: {repo_data['repo_id']}
        Description: {repo_data['description']}
        Evidences: {json.dumps(evidence.get('evidence_atoms', []))}

        Output format in JSON exactly:
        {{
            "project_positioning": "What is it?",
            "attribution": {{
                "primary_cause": "Choose ONE from: Big-name amplification | Product launch / release | Technical breakthrough | Ecosystem timing | Demo excellence",
                "details": "Explanation of why this cause is chosen based on evidence"
            }},
            "potential_score": 85,
            "planning_brief": {{
                "pain_point": "What real world problem does it solve?",
                "mvp_scope": "What should the minimum viable product (MVP) scope be if we build on this?",
                "architecture_breakdown": "Frontend/Backend/Model architecture breakdown",
                "differentiation_strategy": "How to differentiate from similar projects?"
            }}
        }}
        """

        try:
            headers = {
                "Authorization": f"Bearer {self.cloud_llm_api_key}",
                "Content-Type": "application/json"
            }
            resp = requests.post(
                f"{self.cloud_llm_base_url}/chat/completions",
                headers=headers,
                json={
                    "model": "gpt-4o",
                    "response_format": { "type": "json_object" },
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7
                },
                timeout=60
            )
            if resp.status_code == 200:
                content = resp.json()['choices'][0]['message']['content']
                return json.loads(content)
            else:
                logger.error(f"Cloud LLM error: {resp.text}")
        except Exception as e:
            logger.error(f"Cloud LLM call failed: {e}")

        return {
            "project_positioning": "Fallback Positioning",
            "attribution": {
                "primary_cause": "Ecosystem timing",
                "details": "Fallback Attribution due to LLM error"
            },
            "potential_score": 70,
            "planning_brief": {
                "pain_point": "N/A",
                "mvp_scope": "N/A",
                "architecture_breakdown": "N/A",
                "differentiation_strategy": "N/A"
            }
        }

    # ---------------------------------------------------------
    # 4. Report Generation
    # ---------------------------------------------------------
    def generate_daily_report(self, analysis_cards):
        logger.info("Generating Markdown report...")
        report_lines = [
            "# AI Influence: GitHub 开源社区趋势报告",
            f"**日期**: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n",
            "## 今日核心判断",
            "今日趋势主要围绕 AI Agent 与基础设施工具展开。\n",
            "## 今日爆火与潜力项目"
        ]

        if not analysis_cards:
            report_lines.append("今日暂无异常爆火项目。")

        # Sort cards by potential score descending
        analysis_cards.sort(key=lambda x: x.get('potential_score', 0), reverse=True)

        for card in analysis_cards:
            report_lines.append(f"### 📦 [{card.get('repo_id', 'Unknown Repo')}](https://github.com/{card.get('repo_id', '')})")
            report_lines.append(f"- **项目定位**: {card.get('project_positioning', '')}")

            attribution = card.get('attribution', {})
            report_lines.append(f"- **爆火归因** ({attribution.get('primary_cause', 'Unknown')}): {attribution.get('details', '')}")
            report_lines.append(f"- **潜力评分**: {card.get('potential_score', '')}/100")

            brief = card.get('planning_brief', {})
            report_lines.append(f"- **策划启示**:")
            report_lines.append(f"  - **痛点**: {brief.get('pain_point', '')}")
            report_lines.append(f"  - **MVP 边界**: {brief.get('mvp_scope', '')}")
            report_lines.append(f"  - **架构拆解**: {brief.get('architecture_breakdown', '')}")
            report_lines.append(f"  - **差异化策略**: {brief.get('differentiation_strategy', '')}\n")

        report_path = os.path.join(self.data_dir, f"report_{datetime.now(timezone.utc).strftime('%Y%m%d')}.md")
        with open(report_path, "w") as f:
            f.write("\n".join(report_lines))
        logger.info(f"Report saved to {report_path}")

    # ---------------------------------------------------------
    # Main Workflow
    # ---------------------------------------------------------
    def run(self):
        logger.info("=== Starting GitHub Trends Pipeline ===")
        repos = self.discover_repos()

        analysis_cards = []
        for repo in repos:
            repo_data = self.fetch_repo_data(repo)
            if not repo_data:
                continue

            is_hot = self.detect_sudden_hot(repo_data)
            if is_hot:
                evidence = self.extract_evidence_local(repo_data)
                card = self.generate_analysis_card(repo_data, evidence)
                card["repo_id"] = repo
                analysis_cards.append(card)

            # Rate limiting sleep to respect GitHub limits
            time.sleep(1)

        self.generate_daily_report(analysis_cards)
        logger.info("=== Pipeline Completed ===")

if __name__ == "__main__":
    pipeline = GitHubTrendsPipeline()
    pipeline.run()
