---
doc_id: KB-0015
title: Print Jobs Queue but Never Print (Print Spooler Fault)
category: hardware
source: internal-runbook
tags: [printer, spooler, print queue, driver, stuck job]
---

## Symptom
Documents appear in the print queue and remain there. The printer shows ready
but does not produce output. Other users may be affected on the same queue.

## Cause
A corrupted job at the head of the queue stalls the spooler service, or the
print driver has become mismatched after a Windows update.

## Resolution
1. Stop the Print Spooler service on the affected workstation.
2. Delete the contents of the spool PRINTERS folder under the Windows System32 directory to clear the stuck job.
3. Start the Print Spooler service and set its recovery options to restart the service on failure.
4. Remove and re-add the printer using the current signed driver from the print server rather than a locally installed driver.
5. Print a test page from the printer properties dialog to confirm end-to-end operation.

## Escalate if
Jobs stall for all users of a shared queue, which indicates a print server fault
rather than a workstation fault.
