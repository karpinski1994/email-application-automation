## Why

The pipeline currently personalizes CVs and composes emails for all filtered jobs, but the email `to` field is a placeholder (`"PENDING: find email for {company}"`). Without a verified email address, there is no point generating personalized CVs or application emails — they will never be sent. Email finding must happen before CV personalization so we only invest LLM time on jobs where we can actually deliver.

## What Changes

- **BREAKING**: Renumber pipeline step 4 (CV personalization) → step 5
- Add new step 4: Find hiring manager emails using AnyMailFinder decision-maker API
- Introduce `EmailFinderConfig` model and `email_finder` config section
- Rewrite `email_finder.py` from mock to real AnyMailFinder API integration with domain resolution
- Step 5 (CV personalization) now skips jobs without a valid/risky email
- `email_composer.py` accepts a real `to_email` parameter instead of writing `"PENDING: ..."`
- Cache email results in `data/emails.json` to avoid re-querying on subsequent runs
- Domain resolution: company name → candidate domains (.com, .io, .co) with fallback attempts

## Capabilities

### New Capabilities
- `email-finding`: Finds hiring manager emails for filtered jobs using the AnyMailFinder decision-maker API. Includes domain resolution from company names, result caching, and integration into the pipeline as step 4.

### Modified Capabilities
- `cv-personalization`: Now filters jobs by email availability before personalizing. Only jobs with `"valid"` or `"risky"` email status from step 4 get personalized CVs and composed emails. The `to` field in `email.json` is populated with the real email address.

## Impact

- **Files modified**: `src/app/agent.py` (step renumbering + new step 4 block), `src/app/tools/cv_personalizer.py` (email filtering), `src/app/tools/email_composer.py` (`to_email` param), `src/app/tools/email_finder.py` (full rewrite), `src/app/models.py` (new config model), `config.yaml` (new section), `src/app/__main__.py` (step range docs)
- **API dependency**: AnyMailFinder API (`POST /v5.1/find-email/decision-maker`) — requires `ANYMAILFINDER_API_KEY` env var
- **Data format**: New `data/emails.json` file mapping job IDs to email results
- **Pipeline order**: Step 4 is now email finding; old step 4 (CV personalization) becomes step 5
- **Backward compatibility**: `--step=4` now runs email finding instead of CV personalization; `--step=5` runs CV personalization
