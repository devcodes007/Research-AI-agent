"""The assignment's exact 100-app research set (transcribed from the PDF), with its website hints.

Run `python -m atlas seed` to regenerate data/apps.json. `leads` are documentation URLs found earlier by
hand/browsing; they are offered to the agent as starting points, never treated as facts.
"""
import json
from .config import data_dir

GROUPS = [
    ("CRM and Sales", [("Salesforce", "salesforce.com"), ("HubSpot", "hubspot.com"), ("Pipedrive", "pipedrive.com"),
        ("Attio", "attio.com"), ("Twenty", "twenty.com"), ("Podio", "podio.com"), ("Zoho CRM", "zoho.com/crm"),
        ("Close", "close.com"), ("Copper", "copper.com"), ("DealCloud", "api.docs.dealcloud.com")]),
    ("Support and Helpdesk", [("Zendesk", "zendesk.com"), ("Intercom", "intercom.com"), ("Freshdesk", "freshdesk.com"),
        ("Front", "front.com"), ("Pylon", "usepylon.com"), ("LiveAgent", "liveagent.com"), ("Plain", "plain.com"),
        ("Help Scout", "helpscout.com"), ("Gorgias", "gorgias.com"), ("Gladly", "gladly.com")]),
    ("Communications and Messaging", [("Slack", "slack.com"), ("Twilio", "twilio.com"), ("Zoho Cliq", "zoho.com/cliq"),
        ("Lark (Larksuite)", "open.larksuite.com"), ("Pumble", "pumble.com"), ("Discord", "discord.com"),
        ("Telegram", "core.telegram.org"), ("WhatsApp Business", "developers.facebook.com/docs/whatsapp"),
        ("Aircall", "aircall.io"), ("Vonage", "developer.vonage.com")]),
    ("Marketing, Ads, Email and Social", [("Google Ads", "developers.google.com/google-ads"),
        ("Meta Ads", "developers.facebook.com/docs/marketing-apis"), ("LinkedIn Ads", "learn.microsoft.com/linkedin/marketing"),
        ("GoHighLevel", "highlevel.stoplight.io"), ("Mailchimp", "mailchimp.com/developer"), ("Klaviyo", "developers.klaviyo.com"),
        ("systeme.io", "systeme.io"), ("Pinterest", "developers.pinterest.com"),
        ("Threads (Meta)", "developers.facebook.com/docs/threads"), ("SendGrid", "sendgrid.com")]),
    ("Ecommerce", [("Shopify", "shopify.dev"), ("WooCommerce", "woocommerce.com/document/woocommerce-rest-api"),
        ("BigCommerce", "developer.bigcommerce.com"), ("Salesforce Commerce Cloud", "developer.salesforce.com/docs/commerce"),
        ("Magento (Adobe Commerce)", "developer.adobe.com/commerce"), ("Squarespace", "developers.squarespace.com"),
        ("Ecwid", "api-docs.ecwid.com"), ("Gumroad", "gumroad.com/api"),
        ("Amazon Selling Partner", "developer-docs.amazon.com/sp-api"), ("fanbasis", "fanbasis.com")]),
    ("Data, SEO and Scraping", [("DataForSEO", "docs.dataforseo.com"), ("SE Ranking", "seranking.com/api"),
        ("Ahrefs", "ahrefs.com/api"), ("MrScraper", "docs.mrscraper.com"), ("Apify", "docs.apify.com"),
        ("Firecrawl", "firecrawl.dev"), ("Bright Data", "brightdata.com"),
        ("Sherlock", "github.com/sherlock-project/sherlock"), ("Waterfall.io", "waterfall.io"), ("Clay", "clay.com")]),
    ("Developer, Infra and Data platforms", [("GitHub", "docs.github.com/rest"), ("Vercel", "vercel.com/docs/rest-api"),
        ("Netlify", "docs.netlify.com/api"), ("Cloudflare", "developers.cloudflare.com/api"), ("Supabase", "supabase.com/docs"),
        ("Neo4j", "neo4j.com/docs/api"), ("Snowflake", "docs.snowflake.com"), ("MongoDB Atlas", "mongodb.com/docs/atlas/api"),
        ("Datadog", "docs.datadoghq.com/api"), ("Sentry", "docs.sentry.io/api")]),
    ("Productivity and Project Management", [("Notion", "developers.notion.com"), ("Airtable", "airtable.com/developers"),
        ("Linear", "developers.linear.app"), ("Jira", "developer.atlassian.com"), ("Asana", "developers.asana.com"),
        ("Monday.com", "developer.monday.com"), ("ClickUp", "clickup.com/api"), ("Coda", "coda.io/developers"),
        ("Smartsheet", "smartsheet.com/developers"), ("Harvest", "help.getharvest.com/api-v2")]),
    ("Finance and Fintech", [("Stripe", "stripe.com/docs/api"), ("Plaid", "plaid.com/docs"), ("Binance", "binance-docs.github.io"),
        ("Paygent Connect", "Paygent Connect (NMI-powered); not the Japanese Paygent"), ("iPayX", "ipayx.ai/docs"),
        ("QuickBooks", "developer.intuit.com"), ("Xero", "developer.xero.com"), ("Brex", "developer.brex.com"),
        ("Ramp", "docs.ramp.com"), ("PitchBook", "pitchbook.com (research API)")]),
    ("AI, Research and Media-native", [("NotebookLM", "cloud.google.com/gemini (NotebookLM Enterprise API)"),
        ("Otter AI", "help.otter.ai (MCP server)"), ("Fathom", "fathom.video"),
        ("Consensus", "consensus.app (OAuth requested)"), ("Reducto", "reducto.ai (document parsing)"),
        ("Devin", "docs.devin.ai (MCP)"), ("higgsfield", "higgsfield.ai/cli (content suite)"),
        ("Mermaid CLI", "github.com/mermaid-js/mermaid-cli"), ("YouTube Transcript", "transcriptapi.com"),
        ("Grain", "grain.com (meeting notes)")]),
]

# Doc URLs found by hand before the agent ran (offered as retrieval starting points only).
LEADS = {
    91: ["https://docs.cloud.google.com/gemini/enterprise/notebooklm-enterprise/docs/api-notebooks"],
    92: ["https://help.otter.ai/hc/en-us/articles/35287607569687-Otter-MCP-Server"],
    93: ["https://developers.fathom.ai/"],
    94: ["https://help.consensus.app/en/articles/16516328-the-consensus-api",
         "https://help.consensus.app/en/articles/13694300-how-to-use-consensus-in-claude"],
    95: ["https://docs.reducto.ai/"],
    96: ["https://docs.devin.ai/api-reference/authentication"],
    97: ["https://higgsfield.ai/creator-hub/help-center/integrations/what-is-the-higgsfield-api"],
    98: ["https://github.com/mermaid-js/mermaid-cli/blob/master/README.md?plain=1"],
    99: ["https://transcriptapi.com/docs/api/", "https://transcriptapi.com/docs/mcp/"],
    100: ["https://developers.grain.com/", "https://developers.grain.com/mcp/faq.html"],
}


def build():
    apps, i = [], 0
    for category, items in GROUPS:
        for name, hint in items:
            i += 1
            apps.append({"id": i, "name": name, "category": category, "hint": hint, "leads": LEADS.get(i, [])})
    return apps


def write():
    path = data_dir() / "apps.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def load():
    path = data_dir() / "apps.json"
    if not path.exists():
        write()
    return json.loads(path.read_text(encoding="utf-8"))
