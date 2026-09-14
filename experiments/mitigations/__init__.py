"""Shared mitigation studies for authorization memory."""

from domains.base import StudyProfile


MITIGATION_STUDIES = ("source_authority", "event_sourcing")


def mitigation_study_profile(study_id: str) -> StudyProfile:
    if study_id == "source_authority":
        from .source_authority import shared_study_profile

        return shared_study_profile()
    if study_id == "event_sourcing":
        from .event_sourcing import shared_study_profile

        return shared_study_profile()
    raise KeyError(f"unknown mitigation study: {study_id}")
