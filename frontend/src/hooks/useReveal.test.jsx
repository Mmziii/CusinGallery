/**
 * useReveal regression tests (Part R1) -- guard the "invisible home
 * sections" bug: sections whose node mounts AFTER async data loads must
 * still be observed, and content must never stay hidden even when the
 * observer never fires (timeout fail-safe). Uses a controllable
 * IntersectionObserver mock instead of the jsdom stub.
 */
import { act, cleanup, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import useReveal from "./useReveal";

class ControllableIntersectionObserver {
  static instances = [];
  constructor(callback) {
    this.callback = callback;
    this.targets = [];
    ControllableIntersectionObserver.instances.push(this);
  }
  observe(target) {
    this.targets.push(target);
  }
  unobserve(target) {
    this.targets = this.targets.filter((t) => t !== target);
  }
  disconnect() {
    this.targets = [];
  }
  /** test helper: pretend every observed target entered the viewport */
  intersectAll() {
    this.callback(this.targets.map((target) => ({ isIntersecting: true, target })), this);
  }
}

function setReducedMotion(matches) {
  window.matchMedia = (query) => ({
    matches: /prefers-reduced-motion/.test(query) ? matches : false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  });
}

/** mirrors ProductRow: skeleton first (no ref), real section after "load" */
function LateMountSection() {
  const [loaded, setLoaded] = useState(false);
  const ref = useReveal();
  if (!loaded) {
    return (
      <button type="button" onClick={() => setLoaded(true)}>
        load
      </button>
    );
  }
  return (
    <section data-testid="late" className="reveal" ref={ref}>
      content
    </section>
  );
}

beforeEach(() => {
  ControllableIntersectionObserver.instances = [];
  window.IntersectionObserver = ControllableIntersectionObserver;
  setReducedMotion(false);
  document.documentElement.classList.remove("js-reveal");
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  cleanup();
  document.documentElement.classList.remove("js-reveal");
});

describe("useReveal", () => {
  it("observes a node that mounts only after async data loads", () => {
    render(<LateMountSection />);
    // nothing observed yet: the section is not mounted
    expect(ControllableIntersectionObserver.instances.flatMap((i) => i.targets)).toHaveLength(0);

    // data "arrives": the .reveal node mounts late
    act(() => {
      screen.getByText("load").click();
    });
    const node = screen.getByTestId("late");
    const observed = ControllableIntersectionObserver.instances.flatMap((i) => i.targets);
    expect(observed).toContain(node); // the late-mounted node IS observed

    // observer fires -> revealed
    act(() => {
      ControllableIntersectionObserver.instances.at(-1).intersectAll();
    });
    expect(node.classList.contains("is-revealed")).toBe(true);
  });

  it("fail-safe timeout reveals content even if the observer never fires", () => {
    render(<LateMountSection />);
    act(() => {
      screen.getByText("load").click();
    });
    const node = screen.getByTestId("late");
    expect(node.classList.contains("is-revealed")).toBe(false);

    // observer stays silent; after the fail-safe window the node reveals
    act(() => {
      vi.advanceTimersByTime(1600);
    });
    expect(node.classList.contains("is-revealed")).toBe(true);
  });

  it("hides content only when JS initialized the observer (html.js-reveal)", () => {
    render(<LateMountSection />);
    act(() => {
      screen.getByText("load").click();
    });
    // observer was set up -> the gate class is present so CSS may hide pre-reveal
    expect(document.documentElement.classList.contains("js-reveal")).toBe(true);
  });

  it("never hides or waits under prefers-reduced-motion", () => {
    setReducedMotion(true);
    render(<LateMountSection />);
    act(() => {
      screen.getByText("load").click();
    });
    const node = screen.getByTestId("late");
    expect(document.documentElement.classList.contains("js-reveal")).toBe(false);
    expect(node.classList.contains("is-revealed")).toBe(true); // shown immediately
    expect(ControllableIntersectionObserver.instances.flatMap((i) => i.targets)).toHaveLength(0);
  });
});
