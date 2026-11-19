const KEY = "costpilot.organization";

/** The organization the user last worked in (a convenience only; the API re-checks membership). */
export function readStoredOrg(): string | null {
  try {
    return window.localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function storeOrg(id: string | null) {
  try {
    if (id) window.localStorage.setItem(KEY, id);
    else window.localStorage.removeItem(KEY);
  } catch {
    // storage unavailable (private mode): the user just picks again next time
  }
}
