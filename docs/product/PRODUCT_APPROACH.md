# Product Approach

## Product Name

Working name: **MeetingAgent**.

Product idea: a local project-memory agent that connects documents, meetings, decisions, requirements, and deliverables.

## Problem

Project knowledge is scattered across folders, office documents, meeting recordings, chat notes, protocols, and task lists. Important decisions are often present somewhere, but hard to find, validate, and reuse when preparing delivery documentation.

## Target Users

- Project manager who needs protocols, decisions, risks, and task traceability.
- Analyst who works with FTT, requirements, and acceptance documents.
- Architect who needs to connect decisions with project solutions.
- Delivery owner who prepares Passport IS and final project documentation.

## Core Promise

MeetingAgent turns project materials into a reliable local knowledge base and helps generate documents from cited sources.

## Product Pillars

1. **Project Memory**
   Documents, transcripts, protocols, memo, decisions, and tasks are indexed into a single searchable knowledge layer.

2. **Meeting Intelligence**
   New recordings become transcript, memo, protocol, task list, decision log, and project-stage classification.

3. **Document Generation**
   The user describes a target document. MeetingAgent retrieves source evidence and drafts structured content with citations.

4. **Traceability**
   Every generated statement should point back to documents, meeting fragments, timestamps, or source chunks.

5. **Local Control**
   The default mode keeps files, vectors, logs, and generated drafts on the local machine.

## Differentiation

MeetingAgent is not just a generic transcription tool. It is project-aware:

- understands project stages;
- links content to FTT and project decisions;
- separates protocols, memo, decisions, and tasks;
- supports delivery-document generation;
- treats source attribution as a product requirement.

## Product Modes

- **Build RAG**: scan documents, extract text, chunk, embed, index.
- **Ask Project**: ask across documents and meetings with sources.
- **Process Meeting**: transcribe, summarize, classify, and export.
- **Generate Document**: draft a document from project sources.
- **Maintain Knowledge Base**: update, remove, and re-index changed content.

## Success Criteria

- User can ask a project question and see relevant cited sources.
- New meeting recordings become useful project artifacts without manual copy-paste.
- Generated protocols and memo require editing, not rewriting.
- Generated document drafts are grounded in existing project materials.
- Long-running jobs can safely resume after interruption.

