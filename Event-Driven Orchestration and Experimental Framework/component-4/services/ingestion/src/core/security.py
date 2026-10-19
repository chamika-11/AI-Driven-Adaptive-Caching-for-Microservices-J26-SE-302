"""Security validations and limits for specification ingestion."""

import re
from typing import Any, Dict, List, Set, Tuple


class SecurityValidationError(Exception):
    """Raised when an uploaded document violates security boundaries."""

    pass


class SafeSpecScanner:
    """Scans and validates parsed specification dictionaries against security constraints."""

    # Remote URL regex for detecting potential SSRF attempts in $ref
    REMOTE_REF_PATTERN = re.compile(r"^(https?|ftp|file)://", re.IGNORECASE)

    @classmethod
    def scan_for_external_refs(cls, spec: Any) -> Tuple[List[str], List[str]]:
        """Recursively checks for external and remote references.

        Returns:
            Tuple of (prohibited_remote_refs, external_file_refs)
        """
        remote_refs: List[str] = []
        external_file_refs: List[str] = []

        def _traverse(node: Any, current_path: str = ""):
            if isinstance(node, dict):
                for key, val in node.items():
                    if key == "$ref" and isinstance(val, str):
                        val_stripped = val.strip()
                        if cls.REMOTE_REF_PATTERN.match(val_stripped):
                            remote_refs.append(f"{current_path}/$ref: {val_stripped}")
                        elif not val_stripped.startswith("#/"):
                            # Relative or file-based external reference
                            external_file_refs.append(f"{current_path}/$ref: {val_stripped}")
                    else:
                        _traverse(val, f"{current_path}/{key}")
            elif isinstance(node, list):
                for idx, item in enumerate(node):
                    _traverse(item, f"{current_path}[{idx}]")

        _traverse(spec)
        return remote_refs, external_file_refs

    @classmethod
    def validate_security(cls, spec_dict: Dict[str, Any]) -> None:
        """Enforces security boundaries on parsed specification structure.

        Raises SecurityValidationError if unsafe constructs or external references are found.
        """
        remote_refs, external_file_refs = cls.scan_for_external_refs(spec_dict)

        if remote_refs:
            prohibited_list = ", ".join(remote_refs[:3])
            raise SecurityValidationError(
                f"Document contains prohibited remote references: [{prohibited_list}]. "
                "Remote network fetches and external schema resolution are disallowed."
            )

        if external_file_refs:
            external_list = ", ".join(external_file_refs[:3])
            raise SecurityValidationError(
                f"Document contains external file references: [{external_list}]. "
                "Only internal document references ('#/') are supported."
            )
