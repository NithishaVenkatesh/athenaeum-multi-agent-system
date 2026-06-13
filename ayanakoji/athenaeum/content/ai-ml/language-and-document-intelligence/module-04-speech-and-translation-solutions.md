---
kind: module
id: ai-c02-m04
vertical: ai-ml
course_id: ai-c02
title: Speech and translation solutions
level: intermediate
grounded_on: "AI-102 skills outline (2025-12-23), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/ai-102
synthetic: true
order: 4
prereqs: [ai-c02-m02]
objectives:
  - Implement speech-to-text and text-to-speech with Azure AI Speech
  - Shape synthesized speech output using SSML
  - Translate speech-to-text and speech-to-speech in real time
---

# Speech and translation solutions

Larkspur Outfitters is opening a phone line, and the assistant you trained in *Custom language models and question answering* only understands typed text. A caller speaks; your CLU model needs a string. The assistant answers; the caller needs to *hear* it, in a voice that sounds human rather than robotic, with the order number read as digits and not as a single huge number. And some callers speak Portuguese while your agents speak English. Closing all three gaps — speech to text, text to speech, and speech translation — is the job of Azure AI Speech, and it is what turns your text-only pipeline into a voice product.

## Learning objectives

By the end of this module you will be able to:

- Transcribe spoken audio to text and synthesize text to natural-sounding speech with Azure AI Speech.
- Control pronunciation, voice, pace, and emphasis in synthesized output using SSML.
- Translate speech to text across languages and drive speech-to-speech translation.
- Reason about real-time versus batch recognition and choose appropriately.

## Concepts

### One Speech resource, recognizers and synthesizers

Azure AI Speech is a single resource configured with a key (or token credential) and a region. From it you create two main objects. A **SpeechRecognizer** turns audio into text — from a microphone, a file, or a stream — and supports both single-shot recognition for a short utterance and continuous recognition for a long conversation. A **SpeechSynthesizer** turns text into audio, choosing from a large catalog of neural voices across many languages and locales. The region matters: the resource, the voices available, and latency are all tied to it, so provision in a region close to your users.

Recognition is configured by the expected input language, and synthesis by the chosen voice (which implies a language and locale). The mental model: the recognizer is your ears, the synthesizer is your mouth, and the CLU/question-answering brain from earlier modules sits between them. A voice assistant is recognizer → understanding → answer → synthesizer, looping per turn.

### SSML: stop accepting the default reading

Plain text handed to a synthesizer gets a default reading, and defaults are often wrong for real applications. "88231" might be read as "eighty-eight thousand two hundred thirty-one" when you need "eight eight two three one." A pause, a slower rate for a confirmation number, or a switch to a softer voice all require **Speech Synthesis Markup Language (SSML)** — an XML format that wraps your text in elements controlling voice, rate, pitch, volume, pronunciation, and pauses. With `<say-as interpret-as="digits">` you force digit-by-digit reading; with `<break>` you insert a pause; with `<prosody>` you adjust rate and pitch; with `<voice>` you switch speakers mid-utterance. SSML is the difference between a demo voice and one customers trust with a confirmation number.

### Real-time versus batch, and why it changes your design

For an interactive phone line you need **real-time** recognition: audio streams in and partial then final results come back with low latency, turn by turn. For transcribing a backlog of recorded calls overnight, **batch transcription** is the right tool — you point it at stored audio files and collect results asynchronously, trading latency for throughput and cost efficiency. Picking the wrong mode hurts: real-time APIs for a thousand archived files waste money and rate limits, while batch for a live call adds unacceptable delay. Decide based on whether a human is waiting on the other end.

### Speech translation joins the two halves

Speech translation combines recognition and translation in one pipeline. A **TranslationRecognizer** takes audio in a source language and returns text in one or more target languages — that is speech-to-text translation. Add synthesis of the translated text and you have speech-to-speech translation: a caller speaks Portuguese, your agent hears synthesized English, and the reverse direction handles the reply. This builds directly on the text translation concepts from *Analyzing and translating text*, now applied to audio in real time.

## Walkthrough: giving the Larkspur assistant a voice

You provision an Azure AI Speech resource, set its key and region as environment variables, and synthesize a spoken order-status reply. The key requirement: the order number must be read digit by digit and preceded by a short pause, so you author SSML rather than passing plain text.

```python
import os
from azure.cognitiveservices.speech import (
    SpeechConfig, SpeechSynthesizer, ResultReason,
)

speech_config = SpeechConfig(
    subscription=os.environ["SPEECH_KEY"],
    region=os.environ["SPEECH_REGION"],
)
speech_config.speech_synthesis_voice_name = "en-US-AriaNeural"

ssml = """
<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">
  <voice name="en-US-AriaNeural">
    Your order is on its way.<break time="400ms"/>
    The tracking number is
    <say-as interpret-as="digits">88231</say-as>.
    <prosody rate="-10%">Thanks for shopping with Larkspur Outfitters.</prosody>
  </voice>
</speak>
"""

synthesizer = SpeechSynthesizer(speech_config=speech_config, audio_config=None)
result = synthesizer.speak_ssml_async(ssml).get()

if result.reason == ResultReason.SynthesizingAudioCompleted:
    audio = result.audio_data  # bytes you can stream to the caller or save as a file
    print(f"Synthesized {len(audio)} bytes of audio")
else:
    print("Synthesis failed:", result.reason)
```

`speak_ssml_async(...).get()` runs the synthesis and blocks for the result. Because `audio_config=None`, the audio comes back as bytes in `result.audio_data` rather than playing on a local speaker — exactly what you want on a server, where you stream those bytes to the phone channel. The `<say-as interpret-as="digits">` element makes the synthesizer read "eight eight two three one"; the `<break>` inserts a beat before the number so the caller can grab a pen; `<prosody rate="-10%">` slows the sign-off. For the inbound half, you would create a `SpeechRecognizer`, feed it the caller's audio to get text, route that text through your CLU model from module two, and synthesize the answer back through this same path. To serve Portuguese callers, you swap the recognizer for a `TranslationRecognizer` configured with a target language and synthesize the translated text.

## Common pitfalls

- **Accepting default text-to-speech for structured values.** Numbers, dates, currency, and confirmation codes get misread without SSML `say-as`. Anywhere accuracy matters to the listener, author SSML rather than passing raw strings.
- **Using real-time recognition for bulk archives.** Streaming a backlog of recorded calls through the interactive API is slow and costly. Use batch transcription for stored audio and reserve real-time for live conversations.
- **Mismatching recognition language and audio.** A recognizer configured for the wrong language quietly produces garbage transcripts. Set the expected input language, and for multilingual lines consider language identification or speech translation.
- **Forgetting the region is part of the contract.** The Speech resource, its available voices, and latency are region-bound. A voice or feature available in one region may not exist in another — provision near your users and verify voice availability in the docs.
- **Routing audio to a local speaker on a server.** Leaving the default audio output means the service tries to play sound on the host. On a backend, set `audio_config=None` and handle the returned audio bytes yourself.

## Knowledge check

1. Your assistant reads back "Your refund of $45.20 will arrive on 2026-07-01." Customers complain the amount and date sound wrong. What is the fix, and which SSML elements apply?
2. You must transcribe 5,000 archived support calls for quality analysis, and separately power a live phone assistant. Which recognition mode fits each, and why?
3. A caller speaks Portuguese and your agent speaks English, in real time. Which Speech component handles the inbound audio, and how do you produce spoken English back?

<details>
<summary>Answers</summary>

1. Author SSML instead of plain text and wrap the values in `<say-as>` with appropriate `interpret-as` types (e.g. currency/cardinal for the amount, date for the date). — Default synthesis mis-reads structured values; `say-as` forces correct interpretation.
2. Use batch transcription for the 5,000 archived calls (asynchronous, high-throughput, cost-efficient) and real-time recognition for the live assistant (low latency, turn by turn). — The deciding factor is whether a human is waiting; batch trades latency for throughput.
3. A `TranslationRecognizer` configured with the source (Portuguese) and target (English) handles the inbound audio and returns English text; synthesize that text with a `SpeechSynthesizer` to produce spoken English — together this is speech-to-speech translation. — Translation recognition fuses recognition and translation; synthesis closes the loop to audio.

</details>

## Summary

Azure AI Speech gives your text pipeline ears and a mouth: a recognizer transcribes audio, a synthesizer speaks, SSML makes that speech accurate and natural, and translation recognition bridges languages in real time. Choose real-time for live interaction and batch for archives, set the right language and region, and never let structured values fall to default readings. With this module you have completed the language-and-document toolkit — prebuilt and custom text analysis, conversational understanding and Q&A, document extraction, and now speech — and you can assemble them into multimodal solutions alongside the generative models from the prerequisite course.

## Further learning

- [What is the Speech service?](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/overview)
- [Speech Synthesis Markup Language (SSML) overview](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-synthesis-markup)
- [What is speech translation?](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-translation)
- [Text-to-speech quickstart](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/get-started-text-to-speech)
