import { PlannerChat } from "@/features/planner/components/planner-chat";
import { TripStrip } from "@/features/trip/components/trip-strip";
import { TripProvider } from "@/features/trip/trip-provider";

export default function Home() {
  return (
    <TripProvider>
      <div className="sticky top-0 z-10">
        <header className="border-b bg-background">
          <div className="mx-auto flex h-14 max-w-6xl items-center px-4 sm:px-6">
            <span className="flex items-center gap-2.5 font-heading text-lg font-extrabold">
              <span
                aria-hidden
                className="grid size-7 place-items-center rounded-md bg-sign font-mono text-[13px] font-semibold text-sign-foreground"
              >
                TA
              </span>
              Travel Aid
            </span>
          </div>
        </header>
        <TripStrip />
      </div>
      <main className="flex flex-1 flex-col">
        <PlannerChat />
      </main>
    </TripProvider>
  );
}
