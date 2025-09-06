I want to add a program that performs the entire workflow from downloading data until the final DOCX generation. The program must ask if the user wants to load data from Jitbit or Jira and in the Jira case, from which project, these are different runs. The "Q&A-generation" is not part of the workflow, it can be ignored.

For JitBit, it must ask for the first ticket number, tickets should be loaded. The app must then start the script that loads tickets from jitbit and load every ticket with a ticket-id >= this number. In the Jitbit case, the knowledge base must always be loaded. 

In the jitbit-case, the workflow is as follows:

0. As for relevant parameters for JitBit processing (min. ticket-Id)
1. Download jitibit tickets with "jitbit_relevante_tickets.py" which will create "JitBit_relevante_tickets.json"
2. Download jitbit knowledge base with "kb_export_json.py", with will create "JitBit_knowledge_base.json"
3. Run "Process_tickets_with_llm.py" with "JitBit_relevante_tickets.json" to create "Ticket_Data.json" 
4. Run "Tickets_to_docx.py" with "Ticket_Data.json" to create DOCX files from Jira Tickets
5. Run "kb_to_docx.py" to generate DOCX files from "JitBit_Knowledgebase.json"

In the Jira-case, the workflow is as follows:

1. Ask for all relevant parameters (from-date, project (SUP or TMS, with SUP as default))
2. download jitbit ticket data with "jira_relevant_tickets.py" to create "jira_relevante_tickets.json"
3. Run "Process_tickets_with_llm.py" with "Jira_relevante_tickets.json" to create "Ticket_Data_Jira.json" 
4. Run "/scripts/dedupe_tickets.py" with "Ticket_Data_Jira.json" 
4. Run "Tickets_to_docx.py" with "Ticket_Data_Jira._json" to create DOCX files from Jira Tickets

In the Jira case, it must ask for the Project (SUP or TMS) and the date, from which on tickets shall be loaded. 

The app shall then run through the entire workflow: Download ticket-data (and knowledge base for Jitbit), process the ticket data with LLM, de-dupe and finally generate DOCX. 

create an ease to use UI based on modern UI technologies. 