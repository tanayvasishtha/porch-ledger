import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/preact';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { App } from './App';
import type { PorchMcp } from './mcp';
import type { HouseInfo, Inbox, Resident, VisitCard } from './types';

const RESIDENTS: Resident[] = [
  { id: 'priya', display_name: 'Priya Shah' },
  { id: 'sam', display_name: 'Sam Okafor' },
];

const HOUSE_INFO: HouseInfo = {
  name: 'Porch House',
  day_label: 'Monday, June 1',
  residents: RESIDENTS,
};

const CARD: VisitCard = {
  id: 'cb5c0e777ac34a5b',
  kind: 'delivery',
  start_ms: 1780336005000,
  end_ms: 1780337205000,
  title: 'Box for Priya',
  span: '11:05 am',
  facts: ['Box for Priya Shah', 'Rain likely by 4:00 pm'],
  description: 'A box was left at the door.',
  hero_url: '/v1/media/frame.jpg',
  clip_url: null,
  recipient_id: 'priya',
  blocks_door: false,
  claimed_by: null,
  provenance: 'ring',
  version: 1,
};

const INBOX: Inbox = {
  spoken: 'You have a box from UPS.',
  day_label: 'Monday, June 1',
  items: [CARD],
};

function fakeClient(overrides: Partial<PorchMcp> = {}): PorchMcp {
  return {
    serverOrigin: 'http://test',
    houseInfo: vi.fn(async () => HOUSE_INFO),
    anythingForMe: vi.fn(async () => INBOX),
    claimBox: vi.fn(async () => ({ ...CARD, claimed_by: 'priya' })),
    disconnect: vi.fn(async () => undefined),
    ...overrides,
  } as unknown as PorchMcp;
}

afterEach(cleanup);

describe('App', () => {
  it('lists residents and shows the spoken answer plus cards on tap', async () => {
    render(<App client={fakeClient()} />);
    const priya = await screen.findByRole('button', { name: 'Priya' });
    fireEvent.click(priya);
    expect(await screen.findByText('You have a box from UPS.')).toBeTruthy();
    expect(await screen.findByText('Box for Priya')).toBeTruthy();
    expect(screen.getByRole('button', { name: "It's mine" })).toBeTruthy();
    expect(screen.getByText('Rain likely by 4:00 pm')).toBeTruthy();
    // Hero resolves relative URLs at the MCP server origin.
    const hero = screen.getByAltText('Box for Priya') as HTMLImageElement;
    expect(hero.src.startsWith('http://localhost:8000/v1/media/')).toBe(true);
  });

  it('claim calls claim_box then refreshes the inbox', async () => {
    let claimed = false;
    const client = fakeClient();
    (client.anythingForMe as ReturnType<typeof vi.fn>).mockImplementation(async () =>
      claimed ? { ...INBOX, items: [{ ...CARD, claimed_by: 'priya' }] } : INBOX,
    );
    (client.claimBox as ReturnType<typeof vi.fn>).mockImplementation(async () => {
      claimed = true;
      return { ...CARD, claimed_by: 'priya' };
    });
    render(<App client={client} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Priya' }));
    fireEvent.click(await screen.findByRole('button', { name: "It's mine" }));
    await waitFor(() => {
      expect(client.claimBox).toHaveBeenCalledWith('cb5c0e777ac34a5b', 'priya');
      expect(client.anythingForMe).toHaveBeenCalledTimes(2);
    });
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: "It's mine" })).toBeNull();
    });
  });

  it('shows a retry sentence when a tool call fails', async () => {
    const client = fakeClient();
    (client.anythingForMe as ReturnType<typeof vi.fn>)
      .mockRejectedValueOnce(new Error('boom'))
      .mockResolvedValue(INBOX);
    render(<App client={client} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Priya' }));
    expect(await screen.findByText(/did not answer/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText('You have a box from UPS.')).toBeTruthy();
  });

  it('asks a suggested question through the ask tool and marks cited visits', async () => {
    const askQuestion = vi.fn(async () => ({
      answer: 'A box came for you at 11:05 am.',
      visit_ids: [CARD.id],
    }));
    render(<App client={fakeClient({ askQuestion })} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Priya' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Is there a box for me?' }));
    expect(await screen.findByText('A box came for you at 11:05 am.')).toBeTruthy();
    expect(askQuestion).toHaveBeenCalledWith('Is there a box for me?', 'priya');
    const card = screen.getByAltText('Box for Priya').closest('article');
    expect(card?.getAttribute('data-cited')).toBe('true');
  });

  it('offers no claim on a box that is already gone', async () => {
    const gone = { ...CARD, kind: 'box_gone', title: 'Box gone' };
    const client = fakeClient({ anythingForMe: vi.fn(async () => ({ ...INBOX, items: [gone] })) });
    render(<App client={client} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Priya' }));
    expect(await screen.findByText('Box gone')).toBeTruthy();
    expect(screen.queryByRole('button', { name: "It's mine" })).toBeNull();
  });

  it('renders the offline state without a client', () => {
    render(<App client={null} />);
    expect(screen.getByText(/not reachable/)).toBeTruthy();
    expect(screen.getByText(/Simulated Alexa\+ screen/)).toBeTruthy();
  });
});
