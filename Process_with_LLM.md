To transform the raw ticket data into significant information for a RAG system, we need to analyze each ticket, including its entire conversation ("Kommentare"). The Tickets are available in "JitBit_relevante_Tickets.json".

To achieve this, we send each ticket separately to a LLM and ask it to analyze the ticket:
- does this ticket handle a relevant problem, or is it just a simple question (like forgot passwort, create user, etc.)
- what was the core problem?
- how has the problem finally been solved?

We will use together.ai for inference. You find the API-Key and the Model in the .env file.

I tried this prompt, it may be a good first start (improve if helpful)

"""
Please review the information in this ticket. Please check, if the ticket solves a relevant problem and is not only about a ticket about a forgotten password, a new user or something else similary simple. If there is a real problem and a solution, summarize it in such a way that a solution to the problem can be derived. The goal is to identify the actual problem and find the final solution. Remove any unnecessary content, including disclaimers, adresses, etc. Your aim is to determine the core problem(s) that the ticket is about and the final solution.

Here is the ticket with the entire conversation history. You may find URLs in the "Attachment" Field, output these as "URL":

Please output only a json. If the ticket is irrelevant, just output "ticket_id": <the ID> "date": <the date>, "problem": "not relevant", "solution": "", "URL": ""
For relevant tickets, create the same JSON, but with appropriate content. Use Markup in the problem and solution fields.
"""

We then store the new JSON in the file "Ticket_Data.JSON, all in one file for all tickets that did not return wirh "not relevant". The raw data, NOT THE RESULT FROM THE LLM CALL, of the "not relevant" tickets must be copied to "not relevant.json" so that they can be reviewed manually later.

For tests, the user can specify how many tickets the system shall process. Here, we only count relevant tickets, meaning that the couter will only be added up when the LMM did not return "not relevant" as response in the JSON.