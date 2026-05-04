"""CV Personalizer - Generates personalized CV files for each job."""

import asyncio
import json
import logging
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from app.models import Job
from app.config import load_config

logger = logging.getLogger(__name__)

_PARSED_CV_CACHE = None


def _parse_cv_text(cv_text: str) -> dict:
    """Deterministically parse cv.txt into a structured dict.

    No LLM needed — the CV has a consistent structure:
    - Line 1: Name
    - Line 2: Title
    - Line 3-5: Contact info
    - "About" section -> summary
    - "Tech Stack" section -> skills dict
    - "Experience" section -> list of jobs with highlights and dates
    - "Additional Skills, Certifications and Proyects" -> certs
    - "Education" section -> list
    - "Teaching & Leadership Experience" -> list
    """
    lines = cv_text.strip().split("\n")

    name = lines[0].strip() if lines else "Candidate"
    title = lines[1].strip() if len(lines) > 1 else ""

    email = ""
    phone = ""
    location = ""
    education_header = ""
    languages = ""
    linkedin = ""
    for line in lines[2:6]:
        if "Email:" in line:
            m = re.search(r'Email:\s*(\S+)', line)
            if m:
                email = m.group(1)
        if "Phone:" in line:
            m = re.search(r'Phone:\s*(\S+)', line)
            if m:
                phone = m.group(1)
        if "Location:" in line:
            m = re.search(r'Location:\s*(.+?)(?:\s+Phone|\s+Email|\s+Education|\s+Languages|$)', line)
            if m:
                location = m.group(1).strip()
        if "Education:" in line:
            m = re.search(r'Education:\s*(.+?)(?:\s+Languages|$)', line)
            if m:
                education_header = m.group(1).strip()
        if "Languages:" in line:
            m = re.search(r'Languages:\s*(.+?)$', line)
            if m:
                languages = m.group(1).strip()
        if "LinkedIn:" in line:
            m = re.search(r'LinkedIn:\s*(\S+)', line)
            if m:
                linkedin = m.group(1).strip()

    summary = _extract_section(lines, "About", "Tech Stack")

    skills = {}
    in_tech_stack = False
    for line in lines:
        stripped = line.strip()
        if stripped == "Tech Stack":
            in_tech_stack = True
            continue
        if in_tech_stack:
            if stripped == "Experience" or (not any(c == ':' for c in stripped) and stripped):
                break
            if ':' in stripped:
                key, _, val = stripped.partition(':')
                skills[key.strip()] = val.strip()

    experience = _parse_experience(lines)

    certs_raw = _extract_section(lines, "Certifications", "Education")
    certifications = []
    if certs_raw:
        for line in certs_raw.split('\n'):
            line = line.strip()
            if line:
                certifications.append(line)

    projects_raw = _extract_section(lines, "Featured Project", "Certifications")
    projects = []
    if projects_raw:
        projects.append(projects_raw.strip())

    education_raw = _extract_section(lines, "Education", "Teaching & Leadership Experience")
    education_list = []
    if education_raw:
        for line in education_raw.split('\n'):
            line = line.strip()
            if line:
                education_list.append(line)

    teaching_raw = _extract_section(lines, "Teaching & Leadership Experience", None)
    teaching = []
    if teaching_raw:
        for line in teaching_raw.split('\n'):
            line = line.strip()
            if line:
                teaching.append(line)

    all_skills_str = ", ".join(skills.values())

    return {
        "name": name,
        "title": title,
        "email": email,
        "phone": phone,
        "location": location,
        "linkedin": linkedin,
        "languages": languages,
        "summary": summary.strip(),
        "skills": skills,
        "skills_flat": all_skills_str,
        "experience": experience,
        "projects": projects,
        "certifications": certifications,
        "education": education_list,
        "teaching": teaching,
    }


def _extract_section(lines: list[str], start_marker: str, end_marker: str | None) -> str:
    """Extract text between two section markers."""
    start_idx = None
    for i, line in enumerate(lines):
        if line.strip() == start_marker:
            start_idx = i + 1
            break
    if start_idx is None:
        return ""

    end_idx = len(lines)
    if end_marker:
        for i in range(start_idx, len(lines)):
            if lines[i].strip() == end_marker:
                end_idx = i
                break

    return "\n".join(lines[start_idx:end_idx]).strip()


def _parse_experience(lines: list[str]) -> list[dict]:
    """Parse the Experience section into structured job entries.

    The CV has two formats for dates:
    1. Inline: "Senior Front-End Developer - Syndio via Turing NOV 2023 – JAN 2025"
    2. Standalone date line after highlights: "OCT 2022 – JUN 2023"

    For standalone dates, they belong to the previous job if it has no date yet.
    """
    exp_start = None
    for i, line in enumerate(lines):
        if line.strip() == "Experience":
            exp_start = i + 1
            break
    if exp_start is None:
        return []

    end_markers = ["Additional Skills, Certifications and Proyects", "Additional Skills"]
    exp_lines = []
    for i in range(exp_start, len(lines)):
        if any(lines[i].strip().startswith(m) or lines[i].strip() == m for m in end_markers):
            break
        exp_lines.append(lines[i].strip())

    date_re = re.compile(
        r'((?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s+\d{4}\s*[–\-]\s*(?:PRESENT|\w+\s+\d{4}))',
        re.IGNORECASE,
    )

    action_prefixes = (
        "Led ", "Built ", "Architected ", "Delivered ", "Designed ",
        "Directed ", "Owned ", "Drove ", "Applied ", "Modernized ",
        "Spearheaded ", "Managed ", "Developed ", "Implemented ",
        "Collaborated ", "Increased ", "Started ",
    )

    jobs = []

    pending_date = ""

    for line in exp_lines:
        if not line:
            continue

        is_standalone_date = bool(date_re.match(line))
        has_inline_date = date_re.search(line) is not None and not line.startswith(action_prefixes)

        if is_standalone_date:
            if jobs and not jobs[-1]["dates"]:
                jobs[-1]["dates"] = line
            else:
                pending_date = line
            continue

        if has_inline_date:
            dm = date_re.search(line)
            extracted_date = dm.group(1)
            title_part = line[:dm.start()].strip()
            role, _, company = title_part.partition(" - ") if " - " in title_part else (title_part, "", "")
            jobs.append({
                "title": role.strip(),
                "company": company.strip(),
                "dates": extracted_date,
                "highlights": [],
            })
            pending_date = ""
            continue

        if line.startswith(action_prefixes):
            if jobs:
                jobs[-1]["highlights"].append(line)
            continue

        role, _, company = line.partition(" - ") if " - " in line else (line, "", "")
        jobs.append({
            "title": role.strip(),
            "company": company.strip(),
            "dates": pending_date,
            "highlights": [],
        })
        pending_date = ""

    jobs.reverse()
    return jobs


def get_parsed_cv(cv_text: str) -> dict:
    """Get parsed CV data, using cache if available."""
    global _PARSED_CV_CACHE
    if _PARSED_CV_CACHE is None:
        _PARSED_CV_CACHE = _parse_cv_text(cv_text)
    return _PARSED_CV_CACHE


async def _tailor_for_job(cv_data: dict, job: Job) -> dict:
    """Quick LLM call to generate a tailored summary and reordered skills.

    Returns a dict with:
    - tailored_summary: 2-3 sentence summary for this specific job
    - tailored_skills: comma-separated skills reordered by relevance
    """
    config = load_config()
    llm_model = config.llm.model
    llm_base_url = config.llm.base_url
    llm_api_key = config.llm.api_key

    system_prompt = """You tailor CV content for specific job postings.

Return ONLY a JSON object with two fields:
- tailored_summary: A 2-3 sentence professional summary highlighting why this candidate fits THIS specific job
- tailored_skills: A comma-separated list of the candidate's skills, reordered with the most relevant ones first for THIS job

Do NOT invent skills. Only reorder what's provided. Keep the summary factual."""

    user_prompt = f"""Job: {job.title} at {job.company}
Description: {job.description[:800]}

Current summary: {cv_data.get('summary', '')}
Current skills: {cv_data.get('skills_flat', '')}

Return ONLY the JSON object."""

    try:
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: __import__('httpx').post(
                f"{llm_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {llm_api_key}"},
                json={
                    "model": llm_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 300,
                },
                timeout=30.0,
            )
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"].strip()

        if "```" in content:
            parts = content.split("```")
            if len(parts) >= 3:
                content = parts[1]
                if content.startswith("json"):
                    content = content[4:]

        result = json.loads(content.strip())
        return {
            "tailored_summary": result.get("tailored_summary", cv_data.get("summary", "")),
            "tailored_skills": result.get("tailored_skills", cv_data.get("skills_flat", "")),
        }

    except Exception as e:
        logger.warning(f"LLM tailoring failed: {e}, using defaults")
        return {
            "tailored_summary": cv_data.get("summary", ""),
            "tailored_skills": cv_data.get("skills_flat", ""),
        }


async def personalize_cv(cv_text: str, job: Job, force: bool = False, to_email: str = None) -> Path:
    """Generate personalized CV file for a job.

    Args:
        cv_text: Base CV text (from data/cv_parsed.json)
        job: Job listing
        force: Overwrite existing files

    Returns:
        Path to generated HTML file.
    """
    job_dir = Path("data/cvs") / str(job.id)
    job_dir.mkdir(parents=True, exist_ok=True)

    output_path = job_dir / "personalized_cv.html"
    job_info_path = job_dir / "job_info.json"

    if output_path.exists() and not force:
        logger.info(f"  Skipping {job.id} - HTML already exists")
        return output_path

    logger.info(f"  Generating personalized CV for {job.title} at {job.company}...")

    job_info = {
        "id": job.id,
        "title": job.title,
        "company": job.company,
        "url": job.url,
        "location": job.location,
        "description": job.description,
        "requirements": job.requirements,
        "remote_allowed": job.remote_allowed,
        "employment_type": job.employment_type,
        "seniority_level": job.seniority_level,
        "posted_date": job.posted_date,
    }
    job_info_path.write_text(json.dumps(job_info, indent=2, default=str))

    cv_data = get_parsed_cv(cv_text)
    tailored = await _tailor_for_job(cv_data, job)
    cv_data = {**cv_data, **tailored}

    template_dir = Path("src/app/templates")
    if template_dir.exists():
        env = Environment(loader=FileSystemLoader(str(template_dir)))
        template = env.get_template("cv_template.html")
    else:
        from jinja2 import Template
        template = Template(CV_TEMPLATE)

    html_content = template.render(**cv_data)
    output_path.write_text(html_content)

    from app.tools.email_composer import compose_email
    email_data = compose_email(job, cv_text, cv_data=cv_data, to_email=to_email)
    email_path = job_dir / "email.json"
    email_path.write_text(json.dumps(email_data, indent=2, default=str))

    logger.info(f"  ✅ Saved: {job_dir}/")

    return output_path


async def personalize_all_filtered(force: bool = False) -> list:
    """Generate personalized CVs for all filtered jobs with valid emails.

    Reads from data/filtered_jobs.json, data/cv_parsed.json, and data/emails.json.
    Only processes jobs where email status is "valid" or "risky".
    Returns list of generated HTML paths.
    """
    filtered_path = Path("data/filtered_jobs.json")
    if not filtered_path.exists():
        logger.error("data/filtered_jobs.json not found - run filter first (--step=3)")
        return []

    cv_path = Path("data/cv_parsed.json")
    if not cv_path.exists():
        logger.error("data/cv_parsed.json not found - run step 1 first")
        return []

    emails_path = Path("data/emails.json")
    emails = {}
    if emails_path.exists():
        emails = json.loads(emails_path.read_text())

    cv_text = json.loads(cv_path.read_text()).get("text", "")

    from app.models import Job
    jobs_data = json.loads(filtered_path.read_text())
    jobs = [Job(**j) for j in jobs_data]

    eligible = []
    skipped_no_email = []
    for job in jobs:
        job_email = emails.get(job.id, {})
        status = job_email.get("status", "")
        if status in ("valid", "risky"):
            eligible.append((job, job_email.get("email", "")))
        else:
            skipped_no_email.append(job)

    if skipped_no_email:
        logger.info(f"Skipping {len(skipped_no_email)} jobs without valid email: {[j.company for j in skipped_no_email]}")

    logger.info(f"📄 Generating personalized CVs for {len(eligible)} jobs (with valid emails)...")

    html_paths = []
    for i, (job, to_email) in enumerate(eligible):
        try:
            html_path = await personalize_cv(cv_text, job, force=force, to_email=to_email)
            html_paths.append(html_path)
            logger.info(f"  Progress: {i+1}/{len(eligible)}")
        except Exception as e:
            logger.error(f"  Failed for {job.id}: {e}")

    logger.info(f"✅ Generated {len(html_paths)} CVs in data/cvs/")
    return html_paths


if __name__ == "__main__":
    import sys
    sys.path.insert(0, "src")

    logging.basicConfig(level=logging.INFO)

    async def test():
        paths = await personalize_all_filtered()
        print(f"Generated {len(paths)} HTML files")

    asyncio.run(test())
