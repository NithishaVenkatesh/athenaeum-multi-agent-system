"""Per-module assessment question banks.

Authored, static question banks (one per catalog module) seeded into a *separate*
SQLite database (``assessments.db``) and mirrored to Azure Blob Storage. This
package is the system of record's query layer; it never touches a learner's live
attempt data (that lives in ``app.courses``).
"""
