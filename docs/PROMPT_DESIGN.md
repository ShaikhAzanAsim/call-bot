# Prompt design

The commented prompt is `app/voice/prompts/system_prompt.md`. HTML comments are stripped before the text is sent to the model. On a phone call, a long prompt costs latency and makes the voice wander. The file the reviewer reads is longer than the text the model sees.

## What the model is told

- Sound like an intake coordinator. Short sentences. Fillers are rare. Never say "tool" or "draft" out loud.
- One question at a time. City and state are the only pair, because people say them together.
- Never invent a value. `record_field` is the authority. If it rejects the value, the model says the reason and follows `repair_step`.
- Step 1 restates the problem. Step 2 asks for smaller pieces or spelling. Step 3 skips an optional field or parks a required one and comes back. Frustration shortens the next turn and gets one apology.
- Names are spelled only when unclear or corrected. Emails are always spelled back. The tool's `say` text for an email is the normalized address; `get_draft` spells it.
- A correction updates one field and reads back only that field.
- "Start over" and "go back" map to `reset_draft`.
- Proxy registration stores the relationship on the call, then collects the patient's details.
- Spanish switches the rest of the call and sets `preferred_language`. A few key phrases are in the prompt. The whole interview is not duplicated, which keeps the prompt short. The transcriber is Deepgram `language: multi`.
- Emergencies go to 911. Anything else is redirected to registration.
- The optional offer is one sentence, matching the PDF, then a brief email question.
- Save order is fixed: `get_draft`, read it, hear yes, `confirm_registration`, `save_patient`. The server rejects a save without that yes, so the prompt is not the only gate.
- A failed save is spoken, retried once, then handed to staff. The draft stays.
- The closing line is "You're all set, [first name]."

`{{caller_context}}` is replaced per call from caller ID: returning patient, unfinished draft, or neither. The first message is chosen before the model speaks.

## What was cut

- Long few-shot dialogues. They help tone and hurt latency. The repair steps and the `say` field carry the wording instead.
- Insurance eligibility, medical history, and appointment booking. Out of scope for a reliable registration.
- A full Spanish script. The switch and the key lines are there. A complete translation would roughly double the prompt.
- Small talk and clinic marketing.

## Why an extra tool exists

The PDF requires a read-back and an explicit confirmation. A model can skip that and still call save. `confirm_registration` is not in the PDF's tool list because the PDF does not list tools. It exists so the server, the eval scorer, and the prompt all agree: no yes, no save.
