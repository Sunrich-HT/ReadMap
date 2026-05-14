"""
Notion API wrapper — based on raw requests.
Provides typed helpers for common database operations.
"""

from readmap.config import cfg

PROP_TITLE = "论文标题"
PROP_AUTHORS = "作者"
PROP_YEAR = "年份"
PROP_VENUE = "会议期刊"
PROP_KEY_TAKEAWAY = "Key Takeaway"
PROP_URL = "链接"
PROP_READ_DATE = "阅读日期"
PROP_RELATED_PROJECTS = "关联项目"
PROP_RATING = "我的评级"
PROP_READ_STATUS = "阅读状态"
PROP_TOPICS = "主题"
PROP_RELATED_CONCEPTS = "涉及概念"
PROP_READING_MODE = "精读模式"
PROP_REVIEWER_SCORE = "Reviewer评分"
PROP_RELEVANCE = "与我研究的关系"
PROP_QUICK_REF = "速查卡"


def api_get(path: str) -> dict:
    import requests
    r = requests.get(f"https://api.notion.com/v1/{path}", headers=cfg.notion.headers)
    r.raise_for_status()
    return r.json()


def api_post(path: str, body: dict | None = None) -> dict:
    import requests
    r = requests.post(f"https://api.notion.com/v1/{path}", headers=cfg.notion.headers, json=body or {})
    r.raise_for_status()
    return r.json()


def api_patch(path: str, body: dict | None = None) -> dict:
    import requests
    r = requests.patch(f"https://api.notion.com/v1/{path}", headers=cfg.notion.headers, json=body or {})
    r.raise_for_status()
    return r.json()


def api_delete(path: str) -> dict:
    import requests
    r = requests.delete(f"https://api.notion.com/v1/{path}", headers=cfg.notion.headers)
    r.raise_for_status()
    return r.json()


def find_paper_by_title(title: str) -> str | None:
    """Find a paper in the literature database by exact title match."""
    try:
        resp = api_post(f"databases/{cfg.notion.paper_db_id}/query", {
            "filter": {"property": PROP_TITLE, "title": {"equals": title}}
        })
        if resp.get("results"):
            return resp["results"][0]["id"]
    except Exception as e:
        print(f"[WARN] Query failed: {e}")
    return None


def get_all_papers() -> list[dict]:
    """Fetch all papers from the literature database."""
    results = []
    has_more = True
    start_cursor = None
    while has_more:
        body = {"page_size": 100}
        if start_cursor:
            body["start_cursor"] = start_cursor
        resp = api_post(f"databases/{cfg.notion.paper_db_id}/query", body)
        results.extend(resp.get("results", []))
        has_more = resp.get("has_more", False)
        start_cursor = resp.get("next_cursor")
    return results


def get_all_concepts() -> list[dict]:
    """Fetch all concepts from the concept card database."""
    results = []
    has_more = True
    start_cursor = None
    while has_more:
        body = {"page_size": 100}
        if start_cursor:
            body["start_cursor"] = start_cursor
        resp = api_post(f"databases/{cfg.notion.concept_db_id}/query", body)
        results.extend(resp.get("results", []))
        has_more = resp.get("has_more", False)
        start_cursor = resp.get("next_cursor")
    return results


def get_all_projects() -> list[dict]:
    """Fetch all projects from the project database."""
    results = []
    has_more = True
    start_cursor = None
    while has_more:
        body = {"page_size": 100}
        if start_cursor:
            body["start_cursor"] = start_cursor
        resp = api_post(f"databases/{cfg.notion.project_db_id}/query", body)
        results.extend(resp.get("results", []))
        has_more = resp.get("has_more", False)
        start_cursor = resp.get("next_cursor")
    return results


def create_or_update_paper(properties: dict, page_id: str | None = None) -> str:
    """Create or update a literature database entry."""
    if page_id:
        api_patch(f"pages/{page_id}", {"properties": properties})
        return page_id
    else:
        result = api_post("pages", {"parent": {"database_id": cfg.notion.paper_db_id}, "properties": properties})
        return result["id"]


def create_detail_page(parent_id: str, title: str, blocks: list[dict]) -> str:
    """Create a detailed child page under a literature entry."""
    page = api_post("pages", {
        "parent": {"page_id": parent_id},
        "properties": {"title": {"title": [{"text": {"content": title}}]}}
    })
    page_id = page["id"]
    for i in range(0, len(blocks), 90):
        api_post(f"blocks/{page_id}/children", {"children": blocks[i:i + 90]})
    return page_id


def add_to_reading_queue(title: str, url: str = "", source: str = "精读衍生", reason: str = ""):
    """Add a paper to the Reading Queue."""
    api_post("pages", {
        "parent": {"database_id": cfg.notion.queue_db_id},
        "properties": {
            "论文标题": {"title": [{"text": {"content": title}}]},
            "来源": {"select": {"name": source}},
            "状态": {"status": {"name": "待处理"}},
            "链接": {"url": url} if url else {},
            "推荐理由": {"rich_text": [{"text": {"content": reason}}]} if reason else {},
        }
    })


def get_page_url(page_id: str) -> str:
    """Get the Notion page URL."""
    page = api_get(f"pages/{page_id}")
    return page.get("url", "")
