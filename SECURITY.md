# Security Status

This document summarizes the security status of the project's dependencies, including known vulnerabilities and mitigation steps.

---

## Current Vulnerabilities

### 1. `urllib3` (CVE-2024-37891)
- **Severity**: High
- **Status**: Unpatched (no fix available yet)
- **Affected Version**: `2.6.2`
- **Details**: This is a low-risk vulnerability related to HTTP header parsing. It does not affect most use cases.
- **Mitigation**: Monitor for updates to `urllib3` and apply them when available.

### 2. `certifi` (CVE-2024-39689)
- **Severity**: Moderate
- **Status**: Unpatched (no fix available yet)
- **Affected Version**: `2025.11.12`
- **Details**: This is a low-risk vulnerability related to certificate verification in rare edge cases.
- **Mitigation**: Monitor for updates to `certifi` and apply them when available.

---

## Resolved Vulnerabilities

### 1. `Pillow` (CVE-2024-28219)
- **Severity**: Critical
- **Status**: Fixed in `Pillow==11.1.0`
- **Details**: This vulnerability was resolved by updating to `Pillow==11.1.0`.

### 2. `requests` (CVE-2024-35195)
- **Severity**: Moderate
- **Status**: Fixed in `requests==2.32.3`
- **Details**: This vulnerability was resolved by updating to `requests==2.32.3`.

---

## Monitoring and Updates

- **Dependabot**: This project uses GitHub's Dependabot to monitor for new vulnerabilities. Check the [Dependabot alerts](https://github.com/L1Blom/pictures/security/dependabot) regularly for updates.
- **Manual Checks**: Run `safety check` locally to scan for vulnerabilities:
  ```bash
  pip install safety
  safety check
  ```

---

## Reporting Vulnerabilities

If you discover a security vulnerability in this project, please report it by opening an issue in the [GitHub repository](https://github.com/L1Blom/pictures/issues).

---

*Last Updated: 2026-06-18*