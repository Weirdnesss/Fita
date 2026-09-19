import { useEffect, useState } from "react";
import { listWeightLogs } from "../api/accounts";
import { extractErrorMessage } from "../components/Status";

export default function useWeightLogs() {
  const [logs, setLogs] = useState(null);
  const [error, setError] = useState("");

  async function reload() {
    try {
      setLogs(await listWeightLogs());
    } catch (err) {
      setError(extractErrorMessage(err, "Couldn't load weight history."));
    }
  }

  useEffect(() => {
    reload();
  }, []);

  return { logs, error, reload };
}
