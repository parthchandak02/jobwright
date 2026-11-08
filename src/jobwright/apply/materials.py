"""Files and text an application may use (resume / cover letter)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Materials:
    """Absolute paths that exist (or None) plus plain text for the model."""

    resume_path: Path | None = None
    cover_letter_path: Path | None = None
    resume_text: str = ""
    cover_letter_text: str = ""

    def as_filler_dict(self, profile: dict, answers=None) -> dict:
        """The ``materials`` dict the deterministic fillers take (apply/ats/forms.py)."""
        from jobwright.apply.ats.forms import contact_from_profile

        contact = contact_from_profile(profile)
        if answers is not None:
            # Saved answers win over profile.json for contact facts.
            for key, bank_key in (("phone", "phone"), ("linkedin_url", "linkedin_url"),
                                  ("github_url", "github_url"), ("website_url", "portfolio_url"),
                                  ("preferred_name", "preferred_name")):
                value = answers.get(bank_key)
                if value:
                    contact[key] = value
        return {
            "resume_path": str(self.resume_path) if self.resume_path else None,
            "cover_letter_path": str(self.cover_letter_path) if self.cover_letter_path else None,
            "cover_letter_text": self.cover_letter_text,
            "profile": contact,
        }
