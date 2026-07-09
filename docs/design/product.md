# Product

> **Status: Draft.** This document defines what SkillNet is, who it's for, and what it does.

---

## What is SkillNet

A platform that turns company documents into training and tracks what each employee knows how to do.

Open source, self-hosted, one instance per company. Not multi-tenant — by design.

It doesn't compete with enterprise offerings. It exists for the companies that those offerings don't serve.

## Roles

| Role | What they do |
|------|-------------|
| **Admin** | Creates content, assigns training, sees team progress |
| **Employee** | Learns, consults, practices |

## Content types

| Type | Purpose |
|------|---------|
| **Course** | Modules + exercises + evaluation. Structured learning path |
| **Manual** | Reference material. Employees consult when they need it |
| **Chatbot** | Per-content chatbot. Employees ask questions about the material and get answers grounded in it |

## Content generation

The primary way to create content:

- **From documents** — Upload a PDF, manual, or protocol. The AI generates a course or manual from it.

Future generation methods (not in MVP):

- From conversation — tell the AI what you know, it structures the course
- From scratch — give it a topic and level, it generates original content
- Other forms to be explored

## Exercises

Multiple types, defined by the content itself. Examples include tests, practical cases, real-world tasks ("do this and tell me if it worked"), and others to be determined as the product evolves.

## Tracking

Employees complete courses. The system records what they know how to do.

The admin sees team progress. What exactly the admin sees and how it's presented is open.

## Adaptation

The course is generated once. Each employee sees it according to their profile.

How adaptation works in practice is open.
