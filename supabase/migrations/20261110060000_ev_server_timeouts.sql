-- Step 1 fix (11/10): saves queue on one advisory lock. From the Mac each save takes ~1.2 s
-- (network round trips), so in a burst of 20 the later ones waited > 10 s and hit lock_timeout
-- (8/20 refused with an error; none lost). Allow up to 25 s of queueing, below Vercel's 30 s limit.
alter role ev_server set lock_timeout = '25s';
alter role ev_server set statement_timeout = '25s';
