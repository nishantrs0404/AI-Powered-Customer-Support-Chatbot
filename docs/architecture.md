# System Architecture

## 1. Project Overview

The AI-Powered Customer Support Chatbot is designed as a modular monolithic application consisting of a React frontend and a FastAPI backend.

The system combines rule-based NLP, FAQ retrieval, business-data retrieval, and Google Gemini for grounded natural-language response generation.

The chatbot also provides fallback handling, human escalation, conversation persistence, feedback collection, analytics, and error recovery.

---

## 2. High-Level Architecture

```text
                         CUSTOMER
                            |
                            v
                  +-------------------+
                  |   React + Vite    |
                  |     Frontend      |
                  +---------+---------+
                            |
                         HTTP/JSON
                            |
                            v
                  +-------------------+
                  |      FastAPI      |
                  |     API Layer     |
                  +---------+---------+
                            |
                            v
                  +-------------------+
                  |    Input Guard    |
                  | Validation/Limit  |
                  +---------+---------+
                            |
                            v
                  +-------------------+
                  |   NLP / Intent    |
                  |  spaCy + Rules    |
                  +---------+---------+
                            |
                            v
                  +-------------------+
                  |     Retrieval     |
                  | TF-IDF + Cosine   |
                  +---------+---------+
                            |
                            v
                  +-------------------+
                  |   Policy Engine   |
                  +---------+---------+
                            |
              +-------------+-------------+
              |             |             |
              v             v             v
        +-----------+ +-----------+ +-------------+
        |  Gemini   | | Fallback  | | Escalation  |
        |   API     | |  Service  | |   Service   |
        +-----+-----+ +-----+-----+ +------+------+
              |             |              |
              +-------------+--------------+
                            |
                            v
                  +-------------------+
                  | Output Validation |
                  +---------+---------+
                            |
                            v
                  +-------------------+
                  | SQLite Database   |
                  |   SQLAlchemy      |
                  +-------------------+

                  