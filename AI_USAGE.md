# AI Usage and Corrections Log

This document tracks corrections applied to AI-generated code and configuration files during development.

## 1. Cross-Drive Relative Path Failure
- **Category:** Environment Setup & Scripting
- **Incorrect Output:** In the database verification script `verify_db.py`, the AI generated a relative path lookup: `sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../../../PROJECTS/Spreetail_Assignment/backend')))`
- **Correction:** Changed it to the absolute path `"d:/PROJECTS/Spreetail_Assignment/backend"`.
- **Reason for Failure:** The scratch script was written to the `C:` drive while the active workspace is on the `D:` drive. Windows relative path syntax cannot cross drives, resulting in a `ModuleNotFoundError` when importing the database models.

## 2. Legacy SQLAlchemy Query.get() Deprecation Warning
- **Category:** SQLAlchemy API Usage
- **Incorrect Output:** In the import pipeline runner (`pipeline.py`), rules validator (`rules.py`), and API router (`main.py`), the AI generated query lookups using the legacy `db.query(Model).get(id)` syntax.
- **Correction:** Replaced with the modern SQLAlchemy 2.0 `db.get(Model, id)` syntax.
- **Reason for Failure:** The older query interface `Query.get()` is deprecated in SQLAlchemy 2.0 and generates `LegacyAPIWarning` output during runtime. Replacing it with `db.get(Model, id)` resolves the warning and aligns the codebase with modern SQLAlchemy best practices.
