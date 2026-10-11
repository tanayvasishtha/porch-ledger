// The connect() itself failed: no handshake, no residents to list.

export function OfflineApp() {
  return (
    <main class="screen">
      <header class="masthead">
        <h1>Porch Ledger</h1>
        <span class="date" />
      </header>
      <section class="answer" data-tone="error">
        The porch server is not reachable. Check that the demo is running.
        <button class="action retry" type="button" onClick={() => window.location.reload()}>
          Retry
        </button>
      </section>
      <footer class="footer">Simulated Alexa+ screen. Talks to the Porch Ledger MCP server.</footer>
    </main>
  );
}
