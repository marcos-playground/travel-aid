import { SeaBackdrop } from "@/components/sea-backdrop";
import { TripPostmark } from "@/features/trip/components/trip-postmark";
import { TripTags } from "@/features/trip/components/trip-tags";
import type { Trip } from "@/features/trip/trip";
import { TripProvider } from "@/features/trip/trip-provider";
import { PlannerChat, type Message } from "./planner-chat";

/** The planner screen: sea hero, pinned trip tags and the conversation. */
export function PlannerPage({ initialTrip, initialMessages }: { initialTrip?: Trip; initialMessages?: Message[] }) {
  return (
    <TripProvider initialTrip={initialTrip}>
      <div className="relative overflow-hidden bg-[linear-gradient(165deg,var(--sea-deep)_0%,var(--sea-deep)_35%,var(--sea)_100%)] text-white">
        <SeaBackdrop />
        <header className="relative mx-auto flex h-16 max-w-6xl items-center px-4 sm:px-6">
          <span className="flex items-center gap-2.5 font-heading text-lg font-extrabold">
            <span
              aria-hidden
              className="grid size-8 place-items-center rounded-full bg-sunny font-mono text-[13px] font-bold text-night"
            >
              TA
            </span>
            Travel Aid
          </span>
        </header>
        <div className="relative mx-auto flex max-w-6xl items-end justify-between gap-6 px-4 pt-2 pb-6 sm:px-6 sm:pb-8">
          <div className="flex flex-col gap-3">
            <h1 className="font-heading text-4xl leading-[0.98] font-extrabold tracking-tight text-balance sm:text-6xl">
              Hi! Where are you <span className="text-sunny">headed?</span>
            </h1>
            <p className="max-w-[54ch] text-base sm:text-lg">
              Tell me in the chat, or tap a tag to fill in your trip yourself.
            </p>
          </div>
          <TripPostmark className="mb-1 hidden min-[420px]:grid" />
        </div>
      </div>
      {/* The tags stay pinned while the conversation scrolls underneath. */}
      <div className="sticky top-0 z-10 bg-[linear-gradient(180deg,var(--sea)_0%,var(--lagoon)_100%)] shadow-[0_8px_20px_-14px_rgb(0_0_0/0.5)]">
        <TripTags />
      </div>
      <main className="flex flex-1 flex-col">
        <PlannerChat initialMessages={initialMessages} />
      </main>
    </TripProvider>
  );
}
