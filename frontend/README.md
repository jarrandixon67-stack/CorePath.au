# CorePath Intelligence Centre — prototype

This is a static, interactive front-end prototype for the internal CorePath knowledge workspace.

## Preview locally

Open `index.html` in a modern browser. No build tools are required.

## Current interactions

- Navigate between overview, libraries and research activity.
- Open any of the eleven specialist library views.
- Search and filter illustrative source entries.
- Open the source registration form (demonstration only).

## Important limitations

This is a design prototype. Sample source entries are illustrative and are not stored in PostgreSQL. The registration form does not persist data. The next integration step is to connect the interface to the authenticated FastAPI endpoints and replace sample values with live API responses.

Do not expose the internal bearer token in browser JavaScript. A production interface must authenticate through a secure server-side session or a dedicated backend-for-frontend.
