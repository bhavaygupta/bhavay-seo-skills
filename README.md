# Bhavay's Claude SEO Skills

Claude skills from a working B2B SaaS SEO and AEO stack, by [Bhavay Gupta](https://bhavay.com). A Claude skill is a folder of instructions and scripts that Claude and Claude Code load when a task needs them. Everything here is free.

| Skill | What it does | Docs |
|---|---|---|
| [Bhavay's Internal Linking Engine](skills/bhavay-internal-linking/SKILL.md) | An internal linking tool for Claude Code. Bundled scripts crawl your sitemap, read Search Console demand, match paragraphs to target pages and write a prioritized XLSX of links to add. | [bhavay.com](https://bhavay.com/resources/skills/bhavay-internal-linking) |
| [Bhavay's SEO and AEO Content Brief](skills/bhavay-content-brief/SKILL.md) | An SEO content brief generator with a [brief template](skills/bhavay-content-brief/templates/brief-template.md) and a [sample brief](skills/bhavay-content-brief/examples/sample-brief.md). Builds the brief from the live SERP, the AI answer, competitor pages and Search Console. | [bhavay.com](https://bhavay.com/resources/skills/bhavay-content-brief) |
| [Bhavay's GSC and GA4 Connector](skills/bhavay-gsc-ga4/SKILL.md) | Connect Google Search Console and GA4 to Claude Code through the official APIs, with no MCP server to run. Includes an access test, CSV pull scripts and nightly scheduling. | [bhavay.com](https://bhavay.com/resources/skills/bhavay-gsc-ga4) |

## Install

**Claude Code**

```bash
git clone https://github.com/bhavaygupta/bhavay-seo-skills.git
cp -R bhavay-seo-skills/skills/* ~/.claude/skills/
```

**Claude (web or desktop)**

Download a skill zip from its page on [bhavay.com/resources](https://bhavay.com/resources), then upload it in Settings, Capabilities, Skills.

Each skill lists its Python packages in `scripts/requirements.txt`. Then ask for the task in your own words, for example "build an internal linking sheet for example.com". The skill loads itself, checks what you have and tells you which tools it is using.

## License and credit

[CC BY 4.0](LICENSE). Use, share and adapt these skills, including commercially, with credit to [Bhavay Gupta, bhavay.com](https://bhavay.com). Keep the credit line at the top of each SKILL.md.

Need SEO, AEO or GEO help for a B2B SaaS company? [Book a call](https://bhavay.com/contact).
