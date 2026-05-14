# Notion Setup Guide

Paper Nexus syncs your Markdown reading notes to a Notion "Literature Database". This guide shows you how to set it up.

---

## Step 1: Create a Notion Integration

1. Go to [https://www.notion.so/my-integrations](https://www.notion.so/my-integrations)
2. Click **"New integration"**
3. Name it "Paper Nexus" (or whatever you prefer)
4. Select your workspace
5. Copy the **Internal Integration Token** (starts with `secret_` or `ntn_`)
6. Paste it into your `.env` as `NOTION_TOKEN`

---

## Step 2: Create the Databases

You need **4 databases**. Create them as inline databases in any Notion page, then share each page with your integration.

### Database 1: Literature Database (`NOTION_PAPER_DB_ID`)

This is the main database where your paper notes live.

| Property Name | Type | Options / Notes |
|--------------|------|----------------|
| **论文标题** | Title | — |
| **作者** | Rich Text | — |
| **年份** | Number | Integer |
| **会议期刊** | Select | e.g., NeurIPS, ICML, arXiv |
| **Key Takeaway** | Rich Text | One-line summary |
| **链接** | URL | arXiv / DOI / project page |
| **阅读日期** | Date | Auto-filled by sync |
| **阅读状态** | Status | `待处理`, `速扫完成`, `精读完成` |
| **精读模式** | Select | `⚡ 速扫`, `📖 Standard`, `🔬 Deep Dive` |
| **Reviewer评分** | Number | 1-5 scale |
| **与我研究的关系** | Select | e.g., `直接竞争`, `可借鉴`, `密切相关`, `参考`, `无关` |
| **速查卡** | Rich Text | Short reference card |
| **主题** | Multi-select | Your research topics |

### Database 2: Reading Queue (`NOTION_QUEUE_ID`)

For papers you plan to read.

| Property Name | Type | Options |
|--------------|------|---------|
| **论文标题** | Title | — |
| **来源** | Select | `精读衍生`, `推荐`, `会议`, `随机浏览` |
| **状态** | Status | `待处理`, `进行中`, `已完成` |
| **链接** | URL | — |
| **推荐理由** | Rich Text | — |

### Database 3: Project Database (`NOTION_PROJECT_DB_ID`)

For tracking your active research projects.

| Property Name | Type |
|--------------|------|
| **项目名** | Title |
| **状态** | Select |
| **领域** | Multi-select |
| **关联论文** | Relation → Literature Database |

### Database 4: Concept Cards (`NOTION_CONCEPT_DB_ID`)

For extracted concepts and terminology.

| Property Name | Type | Options |
|--------------|------|---------|
| **概念名** | Title | — |
| **一句话定义** | Rich Text | — |
| **成熟度** | Select | `🌱 种子`, `🌿 在长`, `🌳 成熟`, `💎 结晶` |
| **领域** | Multi-select | — |
| **类型** | Select | `方法`, `指标`, `数据集`, `现象`, `理论` |
| **首次见于** | Rich Text | Paper reference |
| **相关论文** | Relation → Literature Database |

---

## Step 3: Share Databases with Your Integration

For **each** database page:
1. Open the database page in Notion
2. Click **"Share"** (top-right)
3. Click **"Add people, emails, groups or integrations"**
4. Search for your integration name ("Paper Nexus")
5. Select it and confirm

> **Important:** The integration must have access to the database **page itself**, not just the parent page.

---

## Step 4: Get Database IDs

1. Open each database in Notion (full page view)
2. Copy the URL, e.g.:
   ```
   https://www.notion.so/workspace/12345678-1234-1234-1234-123456789abc?v=...
   ```
3. The Database ID is the 32-character UUID in the URL:
   ```
   12345678-1234-1234-1234-123456789abc
   ```
4. Paste each ID into your `.env`

---

## Step 5: Test the Connection

```bash
python -m readmap.sync_notion --help
```

If you see the help text without errors, your config is loaded correctly.

To test a real sync:
```bash
# Create a test markdown file
cat > /tmp/test.md << 'EOF'
---
title: "Test Paper"
authors: "A. Author, B. Author"
year: 2024
venue: "arXiv"
url: "https://arxiv.org/abs/2401.00001"
mode: standard
tags: "test"
---

# Test Paper

This is a test note.
EOF

# Sync it
python -m readmap.sync_notion /tmp/test.md
```

---

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| `Missing required configuration: NOTION_TOKEN` | `.env` not created or token missing | Copy `.env.example` → `.env` and fill values |
| `401 Unauthorized` | Token wrong or integration not shared | Re-check token; re-share database with integration |
| `400 Bad Request` during sync | Invalid URL in Markdown link | Ensure all `[text](url)` have `://` in the URL |
| Database entry created but no content | Blocks failed to upload | Check console for "Block X failed" messages |
| Images not showing in Notion | `IMGUR_CLIENT_ID` not set | Optional — set it to enable image upload, or use external URLs |

---

## Property Name Customization

If you prefer English property names, you can modify the constants in `src/readmap/notion_client.py`:

```python
PROP_TITLE = "Title"          # instead of "论文标题"
PROP_AUTHORS = "Authors"      # instead of "作者"
# ... etc
```

Then update your Notion database properties to match.
