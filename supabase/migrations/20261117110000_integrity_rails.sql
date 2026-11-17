-- Phase 14 (re-scoped 11/17): the business rules stay in ONE place (the Python server, which both apps use);
-- the database adds rails so no bug or bad input can ever store impossible values. All rows already comply.
alter table public.leads               add constraint leads_total_nonneg    check (total is null or total >= 0),
                                       add constraint leads_paid_nonneg     check (paid_manual is null or paid_manual >= 0);
alter table public.installments        add constraint installments_amount_nonneg check (amount is null or amount >= 0);
alter table public.contracts           add constraint contracts_money_nonneg check ((total is null or total >= 0) and (retainer is null or retainer >= 0));
alter table public.contract_plan_items add constraint plan_amount_nonneg   check (amount is null or amount >= 0);
alter table public.payments            add constraint payments_amount_pos  check (amount is null or amount > 0);
alter table public.alerts              add constraint alerts_count_pos     check (count is null or count >= 1);
alter table public.emails              add constraint emails_attempts_nonneg check (attempts >= 0);
alter table public.push_subscriptions  add constraint push_endpoint_https  check (endpoint ~ '^https://');
