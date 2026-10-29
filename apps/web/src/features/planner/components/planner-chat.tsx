"use client";

import { useState } from "react";
import { ArrowUpIcon, MicIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupTextarea,
} from "@/components/ui/input-group";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { RecommendationPicker } from "@/features/recommendations/components/recommendation-picker";
import type { RecommendationSet } from "@/features/recommendations/recommendations";
import { useTrip } from "@/features/trip/trip-provider";
import { cn } from "@/lib/utils";
import { useFlightPlanner } from "../use-flight-planner";
import { FlightResults } from "./flight-results";

export type Message =
  | { id: string; role: "user" | "notice"; text: string }
  | { id: string; role: "assistant"; text: string; recommendations?: RecommendationSet };

const EXAMPLE =
  "I want to fly from SDQ to MAD from February 10 to February 15, 2027, for 1 adult. My flight budget is USD 1,000.";

// Shown until the planning workflow is connected, so a sent message never looks ignored.
const NOT_CONNECTED =
  "The assistant isn't connected yet, so I can't reply. You can still set your trip details above.";

function PreviewChat({ initialMessages = [] }: { initialMessages?: Message[] }) {
  const { trip } = useTrip();
  const [messages, setMessages] = useState<Message[]>(initialMessages);
  const [draft, setDraft] = useState("");

  function send() {
    const text = draft.trim();
    if (!text) return;
    const next: Message[] = [...messages, { id: crypto.randomUUID(), role: "user", text }];
    if (!messages.some((message) => message.role === "notice")) {
      next.push({ id: crypto.randomUUID(), role: "notice", text: NOT_CONNECTED });
    }
    setMessages(next);
    setDraft("");
  }

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col px-4 sm:px-6">
      <div className="flex flex-1 flex-col gap-4 py-8 sm:py-12" aria-live="polite">
        <div className="flex flex-col gap-2">
          <h2 className="font-heading text-2xl font-extrabold tracking-tight">Plan it together</h2>
          <p className="max-w-prose text-muted-foreground">
            Tell me where you&apos;re leaving from, where you want to go, your dates, how many people are traveling, and
            your budget for flights and the hotel. I&apos;ll ask about anything missing.
          </p>
        </div>
        {messages.map((message) => (
          <div key={message.id} className="flex flex-col gap-4">
            <p
              className={cn(
                "max-w-[56ch] rounded-2xl px-4 py-2.5 whitespace-pre-wrap",
                message.role === "user"
                  ? "self-end rounded-br-md bg-primary text-primary-foreground"
                  : "self-start rounded-bl-md bg-secondary text-secondary-foreground",
              )}
            >
              {message.text}
            </p>
            {message.role === "assistant" && message.recommendations && (
              <RecommendationPicker set={message.recommendations} budgetUsd={trip.budgetUsd} />
            )}
          </div>
        ))}
      </div>

      <form
        className="sticky bottom-0 flex flex-col gap-2 bg-background pt-2 pb-4 sm:pb-6"
        onSubmit={(event) => {
          event.preventDefault();
          send();
        }}
      >
        <InputGroup className="rounded-2xl border-2 border-foreground/85 bg-card has-[[data-slot=input-group-control]:focus-visible]:border-ring dark:bg-card">
          <InputGroupTextarea
            id="planner-message"
            aria-label="Message"
            placeholder="Describe your trip…"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                send();
              }
            }}
            className="max-h-48 min-h-14 text-base"
          />
          <InputGroupAddon align="block-end" className="justify-between">
            <Tooltip>
              {/* A span trigger, so the tooltip still opens while the button is disabled. */}
              <TooltipTrigger render={<span tabIndex={0} />}>
                <InputGroupButton size="icon-sm" variant="outline" className="rounded-full" disabled aria-label="Speak instead of typing">
                  <MicIcon />
                </InputGroupButton>
              </TooltipTrigger>
              <TooltipContent>Voice input is coming soon</TooltipContent>
            </Tooltip>
            <Button
              type="submit"
              size="sm"
              className="rounded-full bg-hibiscus px-4 font-heading font-extrabold text-white hover:bg-hibiscus/85"
              disabled={!draft.trim()}
            >
              Send
              <ArrowUpIcon data-icon="inline-end" />
            </Button>
          </InputGroupAddon>
        </InputGroup>
        <Button
          type="button"
          variant="link"
          className="h-auto self-start p-0 text-left whitespace-normal text-sea-deep dark:text-lagoon"
          onClick={() => setDraft(EXAMPLE)}
        >
          Try an example: Santo Domingo → Madrid, Feb 10–15, $2,000
        </Button>
      </form>
    </div>
  );
}

export function PlannerChat({ initialMessages }: { initialMessages?: Message[] }) {
  return initialMessages ? <PreviewChat initialMessages={initialMessages} /> : <LiveFlightChat />;
}

function LiveFlightChat() {
  const planner = useFlightPlanner();
  const [draft, setDraft] = useState("");
  const session = planner.session;
  async function send() {
    const text = draft.trim();
    if (!text || planner.busy || !session) return;
    if (await planner.send(text)) setDraft((value) => value.trim() === text ? "" : value);
  }

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col px-4 sm:px-6">
      <div className="flex flex-1 flex-col gap-4 py-8 sm:py-12" aria-live="polite">
        <div className="space-y-2">
          <h2 className="font-heading text-2xl font-extrabold tracking-tight">Find your flight</h2>
          <p className="max-w-prose text-muted-foreground">Tell me where you’re flying from and to (a city, region or airport), your dates and number of adults. You can add a flight budget or refine your preferences as we go.</p>
          <p className="text-xs text-muted-foreground">Your plan is saved in this browser between visits.</p>
        </div>
        {!session && !planner.error && <p role="status" className="text-sm text-muted-foreground">Recovering your plan…</p>}
        {session?.messages.map((message) => (
          <p key={message.id} className={cn("max-w-[56ch] rounded-2xl px-4 py-2.5 whitespace-pre-wrap", message.role === "user" ? "self-end rounded-br-md bg-primary text-primary-foreground" : "self-start rounded-bl-md bg-secondary text-secondary-foreground")}>
            {message.text}
          </p>
        ))}
        {planner.busy && <p role="status" className="text-sm text-muted-foreground">{session?.status === "searching" ? "Your trip is ready. Searching flights…" : "Understanding your trip…"}</p>}
        {planner.error && <p role="alert" className="rounded-xl border border-destructive/40 p-3 text-sm">{planner.error}</p>}
        {session?.status === "interrupted" && !planner.busy && <p className="text-sm text-muted-foreground">Your last search stopped. Your trip and completed results are saved.</p>}
        {session && !planner.dirty && <FlightResults session={session} disabled={planner.busy} onSelect={(id) => { void planner.select(id); }} />}
        <div className="flex gap-2">
          {!planner.busy && session && session.offers.length > 0 && !planner.dirty && <Button variant="outline" size="sm" onClick={() => { void planner.send("Show me more flight options.", "more_options"); }}>More options</Button>}
          {planner.busy ? <Button variant="outline" size="sm" onClick={planner.stop}>Stop search</Button> :
            (planner.error || session?.status === "interrupted" || session?.status === "error" || session?.offers.length) ? <Button variant="outline" size="sm" onClick={planner.retry}>{session?.offers.length ? "Refresh flights" : "Try again"}</Button> : null}
        </div>
      </div>
      <form className="sticky bottom-0 flex flex-col gap-2 bg-background pt-2 pb-4 sm:pb-6" onSubmit={(event) => { event.preventDefault(); void send(); }}>
        <InputGroup className="rounded-2xl border-2 border-foreground/85 bg-card dark:bg-card">
          <InputGroupTextarea aria-label="Message" placeholder="Describe your flight…" value={draft} maxLength={4000}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void send(); } }}
            className="max-h-48 min-h-14 text-base" />
          <InputGroupAddon align="block-end" className="justify-end">
            <Button type="submit" size="sm" className="rounded-full bg-hibiscus px-4 font-heading font-extrabold text-white hover:bg-hibiscus/85" disabled={!draft.trim() || planner.busy || !session}>
              Send <ArrowUpIcon data-icon="inline-end" />
            </Button>
          </InputGroupAddon>
        </InputGroup>
        <Button type="button" variant="link" className="h-auto self-start p-0 text-left whitespace-normal text-sea-deep dark:text-lagoon" onClick={() => setDraft(EXAMPLE)}>
          Try an example: SDQ → MAD, Feb 10–15, 1 adult, $1,000
        </Button>
      </form>
    </div>
  );
}
