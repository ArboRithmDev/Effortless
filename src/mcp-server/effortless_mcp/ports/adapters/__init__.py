"""Adapters concrets du Port Tracker (STO-TRACKER-02).

`jira_client` expose la frontière I/O vers Jira Cloud (`FakeJiraClient` pour les
tests hermétiques, `JiraClient` REST pour le réel). `jira` expose l'adapter
`JiraTracker` qui satisfait le Protocol `Tracker` en s'appuyant sur un client.
"""
