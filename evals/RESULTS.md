# Eval Lab results

Mode: deterministic tool harness.

This scorecard drives the same tool implementations the phone agent uses.
It does not listen to audio. Naturalness of a live call is not in these numbers.
An LLM-vs-LLM run is `python -m evals.run --llm` when `EVAL_LLM_API_KEY` is set.

Pass rate: **21/21** (100%).

| Scenario | Result | Turns | Notes |
|---|---|---|---|
| accept_optional | pass | 17 | The caller opts into email, insurance, and an emergency contact. |
| cooperative | pass | 13 | A clear caller gives every required field in order and confirms. |
| db_failure | pass | 14 | A forced database failure is spoken, retried once, and the draft survives. |
| decline_optional | pass | 14 | Email and insurance are skipped. Sex can be decline to answer. |
| frustrated | pass | 3 | Three bad phone attempts escalate the repair step to 3. |
| future_dob | pass | 13 | A future date of birth is rejected and the same field is asked again. |
| hangup_midcall | pass | 2 | Ending the call before save leaves no patient and marks the session abandoned. |
| hyphenated_name | pass | 12 | Apostrophes and hyphens survive normalization. |
| impossible_date | pass | 1 | February 30 is rejected with a day-specific reason. |
| invalid_phone | pass | 3 | Nine digits, an area code starting with 1, and a 3-digit fragment are each rejected, and the repair step climbs. |
| mumbler | pass | 12 | Dates and phone numbers arrive as spoken digits, including oh and double. |
| out_of_order | pass | 12 | Phone and city arrive before the name. The draft still completes. |
| over_corrector | pass | 14 | The caller corrects the last name three times. Only the last spelling is saved. |
| proxy_mother | pass | 13 | The caller is registering their mother. The relationship stays off the patient row. |
| resume_dropped | pass | 2 | An abandoned draft is offered on the next call from the same number. |
| returning_update | pass | 6 | A phone match offers an update, and the save changes the existing row. |
| silence | pass | 0 | Repeated silence is a platform behavior. This scenario checks the assistant contract, not audio. |
| spanish | pass | 14 | Preferred language is stored as Spanish when the caller asks for it. |
| spoken_email | pass | 13 | Spoken punctuation becomes a real email and is spelled back on request. |
| start_over | pass | 15 | Start over clears the draft, then a new registration can be saved. |
| zip_mismatch | pass | 1 | A Texas ZIP with a Washington state is flagged before any geocoder call matters. |

## Known failures

No deterministic scenario failed in this run. The open gap is conversational: this harness does not prove the live model will follow the prompt on a noisy phone call. Silence handling is a Vapi timeout (`silenceTimeoutSeconds`), checked here as configuration, not as audio.
