import { useState, useEffect, useRef } from 'react';
import { getRepair, getEvents, getDiff } from '../api/endpoints';

export const useRepairPolling = (repairId: string | null) => {
  const [repairData, setRepairData] = useState<any>(null);
  const [events, setEvents] = useState<any[]>([]);
  const [sinceSeq, setSinceSeq] = useState<number>(0);
  const [diff, setDiff] = useState<string>('');
  const [hasDiff, setHasDiff] = useState<boolean>(false);
  const [isPolling, setIsPolling] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const sinceSeqRef = useRef<number>(0);
  const consecutiveErrorsRef = useRef<number>(0);

  useEffect(() => {
    if (!repairId) {
      setRepairData(null);
      setEvents([]);
      setSinceSeq(0);
      setDiff('');
      setHasDiff(false);
      setIsPolling(false);
      setError(null);
      sinceSeqRef.current = 0;
      consecutiveErrorsRef.current = 0;
      return;
    }

    let isMounted = true;
    let inFlight = false;
    let pollingInterval: ReturnType<typeof setInterval> | null = null;

    setIsPolling(true);
    setError(null);
    sinceSeqRef.current = 0;
    consecutiveErrorsRef.current = 0;

    const pollTick = async () => {
      if (inFlight || !isMounted) return;
      inFlight = true;

      try {
        // 1. Fetch current repair state
        const repairRes = await getRepair(repairId);
        if (!isMounted) return;

        const currentData = repairRes.data;
        setRepairData(currentData);
        consecutiveErrorsRef.current = 0;
        setError(null);

        // 2. Fetch diff if available and not yet loaded
        if (currentData.has_diff) {
          try {
            const diffRes = await getDiff(repairId);
            if (isMounted && diffRes.data?.raw_diff) {
              setDiff(diffRes.data.raw_diff);
              setHasDiff(true);
            }
          } catch (diffErr) {
            console.warn('Could not fetch diff yet:', diffErr);
          }
        }

        // 3. Fetch newly generated events
        try {
          const eventsRes = await getEvents(repairId, sinceSeqRef.current);
          if (isMounted && eventsRes.data?.events) {
            if (eventsRes.data.events.length > 0) {
              setEvents(prev => [...prev, ...eventsRes.data.events]);
            }
            if (typeof eventsRes.data.latest_seq === 'number') {
              sinceSeqRef.current = eventsRes.data.latest_seq;
              setSinceSeq(eventsRes.data.latest_seq);
            }
          }
        } catch (eventsErr) {
          console.warn('Could not fetch events yet:', eventsErr);
        }

        // 4. Halt polling on terminal lifecycle status
        if (['verified', 'unresolved', 'failed', 'cancelled'].includes(currentData.status)) {
          if (pollingInterval) {
            clearInterval(pollingInterval);
            pollingInterval = null;
          }
          if (isMounted) {
            setIsPolling(false);
          }
        }
      } catch (err: any) {
        if (!isMounted) return;
        consecutiveErrorsRef.current += 1;
        // Only surface error if 3 consecutive requests fail
        if (consecutiveErrorsRef.current >= 3) {
          const message =
            err?.response?.data?.detail?.message ||
            err?.response?.data?.error?.message ||
            (typeof err?.response?.data?.detail === 'string' ? err?.response?.data?.detail : null) ||
            err?.message ||
            'Failed to fetch repair status';
          setError(message);
          if (pollingInterval) {
            clearInterval(pollingInterval);
            pollingInterval = null;
          }
          setIsPolling(false);
        }
      } finally {
        inFlight = false;
      }
    };

    // Immediate first tick
    pollTick();
    // Subsequent ticks every 1 second
    pollingInterval = setInterval(pollTick, 1000);

    return () => {
      isMounted = false;
      if (pollingInterval) {
        clearInterval(pollingInterval);
        pollingInterval = null;
      }
      setIsPolling(false);
    };
  }, [repairId]);

  return {
    repairData,
    events,
    sinceSeq,
    diff,
    hasDiff,
    isPolling,
    error,
  };
};