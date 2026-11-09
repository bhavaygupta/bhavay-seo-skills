# Free Claude SEO skills

Claude skills from a working B2B SaaS SEO and AEO stack, by [Bhavay Gupta](https://bhavay.com). A Claude skill is a folder of instructions and scripts that Claude and Claude Code load when a task needs them.

| Skill | What it does | Docs |
|---|---|---|
| [internal-linking-engine](skills/internal-linking-engine/SKILL.md) | An internal linking tool for Claude Code. Bundled scripts crawl your sitemap, read Search Console demand, match paragraphs to target pages and write a prioritized XLSX of links to add. | [bhavay.com](https://bhavay.com/resources/skills/internal-linking-engine) |
| [seo-aeo-content-brief](skills/seo-aeo-content-brief/SKILL.md) | An SEO content brief generator with a [brief template](skills/seo-aeo-content-brief/templates/brief-template.md) and a [sample brief](skills/seo-aeo-content-brief/examples/sample-brief.md). Builds the brief from the live SERP, the AI answer, competitor pages and Search Console. | [bhavay.com](https://bhavay.com/resources/skills/seo-aeo-content-brief) |
| [connect-gsc-ga4-claude-code](skills/connect-gsc-ga4-claude-code/SKILL.md) | Connect Google Search Console and GA4 to Claude Code through the official APIs, with no MCP server to run. Includes an access test, CSV pull scripts and nightly scheduling. | [bhavay.com](https://bhavay.com/resources/skills/connect-gsc-ga4-claude-code) |

## Install

**Claude Code**

```bash
git clone https://github.com/bhavay1234/claude-seo-skills.git
cp -R claude-seo-skills/skills/* ~/.claude/skills/
```

**Claude (web or desktop)**

Download a skill zip from its page on [bhavay.com/resources](https://bhavay.com/resources), then upload it in Settings, Capabilities, Skills.

Each skill lists its Python packages in `scripts/requirements.txt`. Then ask for the task in your own words, for example "build an internal linking sheet for example.com". The skill loads itself, checks what you have and tells you which tools it is using.

## License and credit

[CC BY 4.0](LICENSE). Use, share and adapt these skills, including commercially, with credit to [Bhavay Gupta, bhavay.com](https://bhavay.com). Keep the credit line at the top of each SKILL.md.

Need SEO, AEO or GEO help for a B2B SaaS company? [Book a call](https://bhavay.com/contact).
