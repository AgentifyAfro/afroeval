"""
Guards against the class of bug in Finding 1 (2026-07-19 review): a control's
toName referencing an object tag that doesn't exist in that config. Label Studio
validates toName at project creation time — a dangling reference means the
project fails to load, silently, with no local signal. This is the only thing
that would have caught it before Label Studio did.
"""
import re

from hitl.label_config import (
    build_adjudication_label_config,
    build_authoring_label_config,
    build_calibration_label_config,
    build_validation_label_config,
)

# Object tags are the ones controls can point `toName` at (they wrap $variable data).
# Extend this list if a future config introduces another object tag type.
_OBJECT_TAG_PATTERN = re.compile(
    r'<(?:Text|Image|Audio|HyperText|Paragraphs|List|TimeSeries|Table)\b[^>]*\bname="([^"]+)"'
)
_TO_NAME_PATTERN = re.compile(r'toName="([^"]+)"')

_CONFIGS = {
    "calibration": build_calibration_label_config,
    "authoring": build_authoring_label_config,
    "validation": build_validation_label_config,
    "adjudication": build_adjudication_label_config,
}


def _object_names(config: str) -> set[str]:
    return set(_OBJECT_TAG_PATTERN.findall(config))


def _to_name_refs(config: str) -> set[str]:
    return set(_TO_NAME_PATTERN.findall(config))


def test_every_toname_resolves_to_a_declared_object_tag():
    for label, builder in _CONFIGS.items():
        config = builder()
        objects = _object_names(config)
        refs = _to_name_refs(config)
        dangling = refs - objects
        assert not dangling, (
            f"{label} config: toName reference(s) {sorted(dangling)} do not match any "
            f"declared object tag (declared: {sorted(objects)}). Label Studio will reject "
            "this config at project creation."
        )


def test_configs_declare_at_least_one_object_tag():
    # Sanity check the extraction itself isn't silently matching nothing.
    for label, builder in _CONFIGS.items():
        assert _object_names(builder()), f"{label} config: no object tags found — regex may be stale"
