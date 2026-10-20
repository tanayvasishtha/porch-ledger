// Echo-style screen: resident chips on top, the spoken answer below,
// then that resident's visit cards. All porch data flows over MCP.

import { useEffect, useRef, useState } from 'preact/hooks';

import { houseKey, mcpUrlFromEnv, type PorchMcp } from './mcp';
import type { AskAnswer, HouseInfo, Inbox, VisitCard } from './types';

type Status = 'loading' | 'ready' | 'offline' | 'error';

interface Selected {
  residentId: string;
  inbox: Inbox;
}

const MUTED_KEY = 'porch-echo-muted';

// Free questions go to the ask tool, a Bedrock agent that reads saved visits.
export const QUESTIONS = [
  'Did anyone stop by today?',
  'Is there a box for me?',
  'Did a car stop at the house?',
];

export function App({ client }: { client: PorchMcp | null }) {
  const [house, setHouse] = useState<HouseInfo | null>(null);
  const [status, setStatus] = useState<Status>('loading');
  const [selected, setSelected] = useState<Selected | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [reply, setReply] = useState<AskAnswer | null>(null);
  const [muted, setMuted] = useState(() => localStorage.getItem(MUTED_KEY) === '1');
  const mutedRef = useRef(muted);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const lastAsked = useRef<string | null>(null);
  mutedRef.current = muted;

  // Server speech first (Polly behind the API); the browser voice is the
  // offline fallback for the local demo where /v1/speech is not configured.
  const speak = async (text: string) => {
    if (mutedRef.current) return;
    let spoke = false;
    if (client !== null) {
      try {
        const key = houseKey();
        const res = await fetch(`${client.serverOrigin}/v1/speech`, {
          method: 'POST',
          headers: {
            'content-type': 'application/json',
            ...(key ? { authorization: `Bearer ${key}` } : {}),
          },
          body: JSON.stringify({ text }),
        });
        if (!res.ok) throw new Error(`speech ${res.status}`);
        const body = (await res.json()) as { url?: string };
        if (typeof body.url !== 'string') throw new Error('speech: no url');
        const audio = new Audio(new URL(body.url, client.serverOrigin).href);
        audioRef.current?.pause();
        audioRef.current = audio;
        await audio.play();
        spoke = true;
      } catch {
        spoke = false;
      }
    }
    if (!spoke && 'speechSynthesis' in window) {
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(new SpeechSynthesisUtterance(text));
    }
  };

  const loadHouse = () => {
    if (client === null) {
      setStatus('offline');
      return;
    }
    client
      .houseInfo()
      .then((info) => {
        setHouse(info);
        setStatus('ready');
      })
      .catch(() => setStatus('error'));
  };

  useEffect(loadHouse, [client]);

  const ask = async (residentId: string) => {
    if (client === null || busy) return;
    lastAsked.current = residentId;
    setBusy(true);
    try {
      const inbox = await client.anythingForMe(residentId);
      setSelected({ residentId, inbox });
      setReply(null);
      setMessage('');
      void speak(inbox.spoken);
    } catch {
      setMessage('The porch server did not answer. Try again.');
    } finally {
      setBusy(false);
    }
  };

  const askQuestion = async (question: string, residentId: string) => {
    if (client === null || busy) return;
    setBusy(true);
    try {
      const answer = await client.askQuestion(question, residentId);
      setReply(answer);
      setMessage('');
      void speak(answer.answer);
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
    if (next) {
      window.speechSynthesis?.cancel();
      audioRef.current?.pause();
    }
  };

  const answer =
    message !== ''
      ? message
      : busy
        ? 'Asking the porch...'
        : (reply?.answer ?? selected?.inbox.spoken ?? '');
  const cited = new Set(reply?.visit_ids ?? []);

  return (
    <main class="screen">
      <header class="masthead">
        <div class="masthead-text">
          <h1>{house?.name ?? 'Porch Ledger'}</h1>
          <span class="date">{selected?.inbox.day_label ?? house?.day_label ?? ''}</span>
        </div>
        <button
          class="mute-pill"
          type="button"
          aria-pressed={muted}
          aria-label={muted ? 'Unmute voice' : 'Mute voice'}
          onClick={toggleMute}
        >
          {muted ? 'Voice off' : 'Voice on'}
        </button>
      </header>
      <nav class="residents" aria-label="Residents">
        {(house?.residents ?? []).map((resident) => (
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
                loadHouse();
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
      {selected !== null && (
        <nav class="questions" aria-label="Ask the porch">
          {QUESTIONS.map((question) => (
            <button
              key={question}
              class="question-chip"
              type="button"
              disabled={busy}
              onClick={() => askQuestion(question, selected.residentId)}
            >
              {question}
            </button>
          ))}
        </nav>
      )}
      <section class="cards" aria-label="Visits for the selected resident">
        {selected?.inbox.items.map((card) => (
          <article key={card.id} class="visit-card" data-cited={cited.has(card.id)}>
            {card.hero_url !== null && <img src={resolveMedia(card.hero_url)} alt={card.title} />}
            <div class="card-body">
              <h2 class="card-title">{card.title}</h2>
              <span class="card-span">{card.span}</span>
              <div class="facts">
                {card.facts.map((fact) => (
                  <span
                    key={fact}
                    class="fact"
                    data-tone={factTone(fact, card, selected.residentId)}
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
      <footer class="footer">Simulated Alexa+ screen. Talks to the Porch Ledger MCP server.</footer>
    </main>
  );
}

// Sage names the person viewing; terracotta stays for warnings.
function factTone(fact: string, card: VisitCard, residentId: string): string {
  if (card.recipient_id === residentId && /Box for /.test(fact)) return 'mine';
  return /door|rain/i.test(fact) ? 'warn' : 'plain';
}

// Media URLs from the server are relative; resolve them at the MCP origin.
function resolveMedia(url: string): string {
  return new URL(url, mcpUrlFromEnv()).href;
}
