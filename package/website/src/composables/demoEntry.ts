/** Only a server-confirmed demo may use the public, read-only demo account. */
export function createDemoEntry(login: () => Promise<void>, enter: () => Promise<unknown>) {
  let attempted = false;
  return async (status: { demo_mode?: boolean; has_users: boolean }) => {
    if (!status.demo_mode || !status.has_users || attempted) return false;
    attempted = true;
    await login();
    await enter();
    return true;
  };
}
