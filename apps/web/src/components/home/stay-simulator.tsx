"use client";

import { Pause, Play } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** Where the token is: 0 with the student, 1 protected, 2 counted toward the rent. */
type Place = 0 | 1 | 2;

export interface SimulatorStage {
  key: string;
  title: string;
  body: string;
  place: Place;
}

export interface SimulatorBranch {
  key: string;
  /** The stages (by key) where this can happen. */
  stages: readonly string[];
  label: string;
  body: string;
}

export interface StaySimulatorProps {
  /** The token, already formatted from the live policy. */
  token: string;
  stages: readonly SimulatorStage[];
  branches: readonly SimulatorBranch[];
  text: {
    scrub: string;
    step: string;
    places: readonly [string, string, string];
    back: string;
    play: string;
    pause: string;
    happens: string;
    onTrack: string;
  };
}

const PLAY_EVERY_MS = 1900;

/**
 * Walks through a stay and shows where the student's token is at each step, and what happens if
 * something goes wrong. Every word and figure comes from the server, which reads them from the live
 * policy. Nothing here computes money.
 */
export function StaySimulator({ token, stages, branches, text }: StaySimulatorProps) {
  const [index, setIndex] = useState(0);
  const [branchKey, setBranchKey] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);
  const last = stages.length - 1;

  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(() => {
      setIndex((current) => {
        if (current >= last) {
          setPlaying(false);
          return current;
        }
        return current + 1;
      });
    }, PLAY_EVERY_MS);
    return () => {
      window.clearInterval(timer);
    };
  }, [playing, last]);

  const stage = stages[index];
  if (stage === undefined) return null;
  const open = branches.filter((branch) => branch.stages.includes(stage.key));
  const branch = open.find((candidate) => candidate.key === branchKey) ?? null;
  const place: Place = branch === null ? stage.place : 0;

  function scrub(next: number) {
    setPlaying(false);
    setBranchKey(null);
    setIndex(next);
  }

  function togglePlay() {
    setBranchKey(null);
    if (!playing && index >= last) setIndex(0);
    setPlaying((value) => !value);
  }

  return (
    <div className="grid gap-10 lg:grid-cols-[1.05fr_1fr] lg:items-start lg:gap-16">
      <div className="min-w-0">
        <p className="text-sm font-medium text-muted-foreground tabular-nums">
          {text.step
            .replace("{current}", String(index + 1))
            .replace("{total}", String(stages.length))}
        </p>
        <div aria-live="polite" className="mt-2 min-h-56 sm:min-h-48">
          <h3 className="text-title-1 font-medium">{stage.title}</h3>
          <p className="mt-3 max-w-prose text-lg leading-relaxed text-muted-foreground">
            {stage.body}
          </p>
          {branch === null ? null : (
            <p className="mt-4 max-w-prose rounded-2xl bg-marigold-soft p-4 text-base leading-relaxed text-marigold-soft-foreground">
              {branch.body}
            </p>
          )}
        </div>

        <div className="mt-6 flex items-center gap-4">
          <Button
            type="button"
            variant="outline"
            size="icon"
            shape="pill"
            onClick={togglePlay}
            aria-label={playing ? text.pause : text.play}
            className="motion-reduce:hidden"
          >
            {playing ? <Pause aria-hidden="true" /> : <Play aria-hidden="true" />}
          </Button>
          <input
            type="range"
            min={0}
            max={last}
            step={1}
            value={index}
            onChange={(event) => {
              scrub(Number(event.target.value));
            }}
            aria-label={text.scrub}
            aria-valuetext={stage.title}
            className="range-sun min-w-0 flex-1"
            style={{ "--fill": String((index / last) * 100) + "%" }}
          />
        </div>
        <ol className="mt-3 hidden justify-between gap-2 lg:flex">
          {stages.map((item, position) => (
            <li key={item.key}>
              <button
                type="button"
                onClick={() => {
                  scrub(position);
                }}
                aria-current={position === index ? "step" : undefined}
                className={cn(
                  "min-h-6 rounded-md text-xs font-medium outline-none transition-colors duration-(--duration-fast) hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring motion-reduce:transition-none",
                  position === index ? "text-foreground" : "text-muted-foreground",
                )}
              >
                {item.title}
              </button>
            </li>
          ))}
        </ol>

        <div className="mt-6 min-h-11">
          {open.length === 0 ? null : (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-medium text-muted-foreground">{text.happens}</span>
              {open.map((candidate) => (
                <Button
                  key={candidate.key}
                  type="button"
                  variant={candidate.key === branchKey ? "default" : "outline"}
                  size="sm"
                  shape="pill"
                  aria-pressed={candidate.key === branchKey}
                  onClick={() => {
                    setPlaying(false);
                    setBranchKey((current) => (current === candidate.key ? null : candidate.key));
                  }}
                >
                  {candidate.label}
                </Button>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="min-w-0 rounded-[2rem] bg-surface-warm p-6 sm:p-10">
        <div className="sim-track relative" style={{ "--place": place }}>
          <div className="sim-line rounded-full bg-input/50" />
          <div className="sim-fill rounded-full bg-sun" />
          {text.places.map((label, position) => (
            <div
              key={label}
              className="sim-stop flex flex-col items-center text-center"
              style={{ "--stop": position }}
            >
              <span aria-hidden="true" className="sim-node rounded-full bg-input" />
              <span
                className={cn(
                  "sim-label px-1 text-sm leading-snug font-medium transition-colors duration-(--duration-slow) motion-reduce:transition-none",
                  position === place ? "text-foreground" : "text-muted-foreground",
                )}
              >
                {label}
              </span>
            </div>
          ))}
          <div className="sim-coin flex justify-center">
            <span className="grid size-(--coin) place-items-center rounded-full bg-sun text-center font-display text-base font-semibold text-sun-foreground shadow-lg ring-4 ring-surface-warm sm:text-xl">
              {token}
            </span>
          </div>
        </div>
        <p className="mt-8 text-center text-sm text-muted-foreground">
          {branch === null ? text.onTrack : text.back}
        </p>
      </div>
    </div>
  );
}
