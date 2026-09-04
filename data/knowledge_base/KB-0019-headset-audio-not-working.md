---
doc_id: KB-0019
title: Headset Microphone or Audio Not Working in Meetings
category: hardware
source: internal-runbook
tags: [headset, audio, microphone, teams, device selection]
---

## Symptom
The user cannot be heard in meetings, or hears nothing, while the headset works
in other applications.

## Cause
Almost always the wrong input or output device selected inside the meeting
application, or the operating system privacy setting blocking microphone access.

## Resolution
1. In the meeting application's device settings, explicitly select the headset for both speaker and microphone rather than leaving it on the system default.
2. Check the operating system sound settings and confirm the headset is set as the default communication device.
3. Verify the microphone privacy setting allows desktop applications to access the microphone.
4. Confirm the physical mute switch on the headset or its inline control is not engaged.
5. Test with the built-in test call feature in the meeting application to confirm capture and playback.

## Escalate if
The headset is not enumerated by the operating system on two different machines,
indicating a hardware failure.
