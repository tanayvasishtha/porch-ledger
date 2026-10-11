// Echo-style screen: resident chips on top, the spoken answer below,
// then that resident's visit cards. All porch data flows over MCP.

import { useEffect, useRef, useState } from 'preact/hooks';

import { mcpUrlFromEnv, type PorchMcp } from './mcp';
import type { Inbox, Resident, VisitCard } from './types';

type Status = 'loading' | 'ready' | 'offline' | 'error';

interface Selected {
  residentId: string;
  inbox: Inbox;
}

const MUTED_KEY = 'porch-echo-muted';

const todayLine = () =>
  new Date().toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  });

export function App({ client }: { client: PorchMcp | null }) {
  const [residents, setResidents] = useState<Resident[]>([]);
  const [status, setStatus] = useState<Status>('loading');
  const [selected, setSelected] = useState<Selected | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [muted, setMuted] = useState(() => localStorage.getItem(MUTED_KEY) === '1');
  const mutedRef = useRef(muted);
  const lastAsked = useRef<string | null>(null);
  mutedRef.current = muted;

  const speak = (text: string) => {
    if (mutedRef.current || !('speechSynthesis' in window)) return;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(new SpeechSynthesisUtterance(text));
  };

  const loadResidents = () => {
    if (client === null) {
      setStatus('offline');
      return;
    }
    client
      .residents()
      .then((found) => {
        setResidents(found);
        setStatus('ready');
      })
      .catch(() => setStatus('error'));
  };

  useEffect(loadResidents, [client]);

  const ask = async (residentId: string) => {
    if (client === null || busy) return;
    lastAsked.current = residentId;
    setBusy(true);
    try {
      const inbox = await client.anythingForMe(residentId);
      setSelected({ residentId, inbox });
      setMessage('');
      speak(inbox.spoken);
    } catch {
      setMessage('The porch server did not answer. Try again.');
    } finally {
      setBusy(false);
    }
  };

  const claim = async (card: VisitCard, residentId: string) => {
    if (client === null) return;
    try {
      await client.claimBox(card.id, residentId);
      const inbox = await client.anythingForMe(residentId);
      setSelected({ residentId, inbox });
    } catch {
      setMessage('The claim did not go through. Try again.');
    }
  };

  const toggleMute = () => {
    const next = !muted;
    setMuted(next);
    localStorage.setItem(MUTED_KEY, next ? '1' : '0');
    if (next) window.speechSynthesis?.cancel();
  };

  const answer =
    message !== '' ? message : busy ? 'Asking the porch...' : (selected?.inbox.spoken ?? '');

  return (
    <main class="screen">
      <header class="masthead">
        <h1>Porch Ledger</h1>
        <span class="date">{todayLine()}</span>
      </header>
      <nav class="residents" aria-label="Residents">
        {residents.map((resident) => (
          <button
            key={resident.id}
            class="resident-chip"
            type="button"
            data-selected={selected?.residentId === resident.id}
            onClick={() => ask(resident.id)}
          >
            {resident.display_name.split(' ')[0]}
          </button>
        ))}
      </nav>
      <section
        class="answer"
        role="status"
        aria-live="polite"
        data-tone={message !== '' ? 'error' : 'spoken'}
      >
        {status === 'loading' ? (
          <div class="skeleton" />
        ) : status === 'offline' ? (
          'The porch server is not reachable. Check that the demo is running.'
        ) : (
          answer
        )}
        {(status === 'error' || message !== '') && (
          <button
            class="action retry"
            type="button"
            onClick={() => {
              if (status === 'error') {
                loadResidents();
              } else {
                setMessage('');
                const retry = selected?.residentId ?? lastAsked.current;
                if (retry !== null) void ask(retry);
              }
            }}
          >
            Retry
          </button>
        )}
      </section>
      <section class="cards" aria-label="Visits for the selected resident">
        {selected?.inbox.items.map((card) => (
          <article key={card.id} class="visit-card">
            {card.hero_url !== null && <img src={resolveMedia(card.hero_url)} alt={card.title} />}
            <div class="card-body">
              <h2 class="card-title">{card.title}</h2>
              <span class="card-span">{card.span}</span>
              <div class="facts">
                {card.facts.map((fact) => (
                  <span
                    key={fact}
                    class="fact"
                    data-tone={/door|rain/i.test(fact) ? 'warn' : 'plain'}
                  >
                    {fact}
                  </span>
                ))}
              </div>
              {card.recipient_id !== null && card.claimed_by === null && (
                <button
                  class="action"
                  type="button"
                  onClick={() => claim(card, selected.residentId)}
                >
                  It's mine
                </button>
              )}
            </div>
          </article>
        ))}
      </section>
      <button
        class="mute"
        type="button"
        aria-label={muted ? 'Unmute voice' : 'Mute voice'}
        onClick={toggleMute}
      >
        {muted ? 'voice off' : 'voice on'}
      </button>
      <footer class="footer">Simulated Alexa+ screen. Talks to the Porch Ledger MCP server.</footer>
    </main>
  );
}

// Media URLs from the server are relative; resolve them at the MCP origin.
function resolveMedia(url: string): string {
  return new URL(url, mcpUrlFromEnv()).href;
}
