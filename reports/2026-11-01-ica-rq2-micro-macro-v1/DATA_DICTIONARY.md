# Data dictionary

All numeric CSVs preserve topic, matched seed, condition, run and horizon. Blank cells are missing/undefined, never zero.
Matched seed/run is the independent replicate. T30 and T60 panels reuse prefixes and are not independent samples.
A round is N successful weighted activations, not one activation per agent. Population remains N=500.
A2 exact rates use event opportunities with nonempty pure-target feed; toward-target is a different numerator. No per-slot duplicated outcome denominators.
Response-cell denominators repeat over observed outcome rows of a conditioning cell; never sum repeated denominators.
Private state, latest public stock, new public flow and actually read historical posts are distinct. Public stance is not sender private stance.
A3 selection is purposive numeric coverage; all semantic judgments pending human review. Raw text is excluded from Review Packet.
B0 adjacency statistics and zero-opportunity rates may be undefined. Group labels remain backend memberships when A0 hides them.
Stage-A/B joint manipulation did not pass; source associations do not establish trust/identity mechanisms.
P0 is separate fixed-step diagnostic context, not an extra network replicate.

## A1_cumulative_flow.csv.gz

`topic_key`, `matched_seed`, `cell_id`, `run_id`, `cohort`, `horizon`, `identity_a`, `network_b`, `n_agents`, `round`, `stance`, `cumulative_inflow`, `cumulative_outflow`, `cumulative_net_flow`, `population_count`, `round0_count`, `focus_pair`

## A1_dominant_stance_formation.csv.gz

`topic_key`, `matched_seed`, `cell_id`, `run_id`, `cohort`, `horizon`, `identity_a`, `network_b`, `n_agents`, `agent_id`, `target_stance`, `origin_stance`, `baseline_occupant`, `first_entry_ordinal`, `first_entry_round`, `retained_continuously`, `leave_count`, `reentry_count`, `endpoint_occupant`, `endpoint_contribution_count`

## A1_dominant_stance_round_shares.csv.gz

`topic_key`, `matched_seed`, `cell_id`, `run_id`, `cohort`, `horizon`, `identity_a`, `network_b`, `n_agents`, `round`, `target_stance`, `origin_stance`, `contribution_count`, `contribution_share`, `target_count`, `target_share`

## A1_net_stance_flows.csv.gz

`topic_key`, `matched_seed`, `cell_id`, `run_id`, `cohort`, `horizon`, `identity_a`, `network_b`, `n_agents`, `round`, `stance`, `inflow`, `outflow`, `net_flow`, `cumulative_net_flow`, `population_count`, `population_share`, `previous_count`, `round0_count`

## A1_origin_destination_paths.csv.gz

`topic_key`, `matched_seed`, `cell_id`, `run_id`, `cohort`, `horizon`, `identity_a`, `network_b`, `n_agents`, `agent_id`, `group`, `stance_r0`, `stance_r30`, `stance_end`, `direct_3_to_5_count`, `direct_5_to_3_count`, `via4_3_to_5_count`, `via4_5_to_3_count`, `lower_to_upper_event_count`, `upper_to_lower_event_count`, `first_visit_3_ordinal`, `first_visit_5_ordinal`

## A1_round_transition_matrices.csv.gz

`topic_key`, `matched_seed`, `cell_id`, `run_id`, `cohort`, `horizon`, `identity_a`, `network_b`, `n_agents`, `round`, `from_stance`, `to_stance`, `count`, `n_events`, `n_unique_agents`

## A2_directional_update_rates.csv.gz

`topic_key`, `matched_seed`, `cell_id`, `run_id`, `cohort`, `horizon`, `identity_a`, `network_b`, `n_agents`, `prior_stance`, `target_stance`, `feed_condition`, `n_opportunities`, `n_exact_i_to_j`, `n_toward_target`, `exact_rate`, `toward_rate`

## A2_event_exposure_numeric.csv.gz

`topic_key`, `matched_seed`, `cell_id`, `run_id`, `cohort`, `horizon`, `identity_a`, `network_b`, `n_agents`, `ordinal`, `round`, `agent_id`, `prior_activation_count`, `activation_count`, `receiver_group`, `prior_stance`, `after_stance`, `public_before`, `published`, `public_after`, `reason_changed`, `feed_length`, `exposure_class`, `feed_mean`, `feed_variance`, `distance_numerator`, `distance_denominator`, `signed_distance`, `below_count`, `above_count`, `equal_count`, `below_share`, `above_share`, `equal_share`, `same_group_count`, `other_group_count`, `same_group_share`, `other_group_share`, `unique_sources`, `duplicate_source_slots`, `source_hhi`, `mean_post_age`, `max_post_age`, `round0_post_slots`, `repeat_post_slots`, `repeated_source_slots`, `post_key_method`, `prior_source_exposures`, `prior_unique_sources`, `prior_source_hhi`, `prior_below_slots`, `prior_above_slots`, `prior_equal_slots`, `changed`, `update_delta`, `moved_toward_feed_mean`, `feed_stance_1_count`, `feed_stance_2_count`, `feed_stance_3_count`, `feed_stance_4_count`, `feed_stance_5_count`, `feed_stance_6_count`, `feed_stance_7_count`

## A2_exposure_history_summary.csv.gz

`topic_key`, `matched_seed`, `cell_id`, `run_id`, `cohort`, `horizon`, `identity_a`, `network_b`, `n_agents`, `round`, `prior_stance`, `prior_exposure_bin`, `prior_below_slots`, `prior_above_slots`, `repeated_source_slots`, `distance_numerator`, `feed_length`, `n_events`, `n_changed`, `change_rate`, `n_moved_toward_feed_mean`, `toward_mean_rate`, `interpretation`

## A2_exposure_response_cells.csv.gz

`topic_key`, `matched_seed`, `cell_id`, `run_id`, `cohort`, `horizon`, `identity_a`, `network_b`, `n_agents`, `round`, `prior_stance`, `exposure_class`, `distance_numerator`, `distance_denominator`, `feed_length`, `after_stance`, `numerator`, `denominator`, `probability`

## A2_seed_level_contrasts.csv.gz

`topic_key`, `matched_seed`, `cell_id`, `run_id`, `cohort`, `horizon`, `identity_a`, `network_b`, `n_agents`, `prior_stance`, `target_stance`, `mirror_prior_stance`, `mirror_target_stance`, `n_opportunities`, `mirror_n_opportunities`, `exact_rate`, `mirror_exact_rate`, `exact_rate_difference`, `toward_rate`, `mirror_toward_rate`, `figure6_pair`

## B1_global_convergence_by_run.csv.gz

`topic_key`, `matched_seed`, `cell_id`, `run_id`, `cohort`, `horizon`, `identity_condition`, `network_condition`, `round`, `n`, `mean`, `variance`, `count_1`, `count_2`, `count_3`, `count_4`, `count_5`, `count_6`, `count_7`, `share_1`, `share_2`, `share_3`, `share_4`, `share_5`, `share_6`, `share_7`, `variance_change_from_r0`, `variance_fraction_of_r0`, `variance_normalized_change_from_r0`, `variance_delta_per_round`, `variance_average_change_per_round_since_r0`, `share_1_delta_per_round`, `share_1_change_from_r0`, `share_2_delta_per_round`, `share_2_change_from_r0`, `share_3_delta_per_round`, `share_3_change_from_r0`, `share_4_delta_per_round`, `share_4_change_from_r0`, `share_5_delta_per_round`, `share_5_change_from_r0`, `share_6_delta_per_round`, `share_6_change_from_r0`, `share_7_delta_per_round`, `share_7_change_from_r0`, `n_reason_change_known`, `n_reason_changed`, `n_events`, `n_changed`, `n_low_to_high`, `n_high_to_low`, `n_upward`, `n_downward`, `change_event_rate`, `reason_change_rate`, `low_to_high_event_rate`, `high_to_low_event_rate`, `upward_event_rate`, `downward_event_rate`, `excess_same_stance_unrestricted`, `excess_same_stance_within_group`

## B1_paired_network_effects.csv.gz

`topic_key`, `matched_seed`, `cohort`, `horizon`, `round`, `identity_condition`, `network_condition`, `run_id`, `b0_run_id`, `variance_network`, `variance_b0`, `network_effect_variance`, `network_effect_variance_pct_of_b0`, `normalized_r0_change_difference`

## B1_time_trajectories.csv.gz

`topic_key`, `matched_seed`, `cell_id`, `run_id`, `cohort`, `horizon`, `identity_condition`, `network_condition`, `round`, `n`, `mean`, `variance`, `count_1`, `count_2`, `count_3`, `count_4`, `count_5`, `count_6`, `count_7`, `share_1`, `share_2`, `share_3`, `share_4`, `share_5`, `share_6`, `share_7`, `variance_change_from_r0`, `variance_fraction_of_r0`, `variance_normalized_change_from_r0`, `variance_delta_per_round`, `variance_average_change_per_round_since_r0`, `share_1_delta_per_round`, `share_1_change_from_r0`, `share_2_delta_per_round`, `share_2_change_from_r0`, `share_3_delta_per_round`, `share_3_change_from_r0`, `share_4_delta_per_round`, `share_4_change_from_r0`, `share_5_delta_per_round`, `share_5_change_from_r0`, `share_6_delta_per_round`, `share_6_change_from_r0`, `share_7_delta_per_round`, `share_7_change_from_r0`

## B1_topology_contrasts.csv.gz

`topic_key`, `matched_seed`, `cohort`, `horizon`, `round`, `identity_condition`, `b0_run_id`, `b1_run_id`, `b2_run_id`, `variance_b0`, `variance_b1`, `variance_b2`, `topology_effect_b2_minus_b1`, `topology_effect_pct_of_b0`, `normalized_r0_change_difference`

## B2_edge_opinion_similarity.csv.gz

`topic_key`, `matched_seed`, `cell_id`, `run_id`, `cohort`, `horizon`, `identity_condition`, `network_condition`, `round`, `edge_scope`, `n_edges`, `same_stance_fraction`, `mean_abs_distance`, `assortativity`

## B2_local_excess_homophily.csv.gz

`topic_key`, `matched_seed`, `cell_id`, `run_id`, `cohort`, `horizon`, `identity_condition`, `network_condition`, `round`, `edge_scope`, `permutation_mode`, `actual_same_stance_fraction`, `expected_same_stance_fraction`, `excess_same_stance_fraction`

## B2_permutation_baselines.csv.gz

`topic_key`, `matched_seed`, `cell_id`, `run_id`, `cohort`, `horizon`, `identity_condition`, `network_condition`, `round`, `edge_scope`, `permutation_mode`, `permutations`, `analysis_seed`, `expected_same_stance_fraction`, `null_description`, `null_same_stance_fraction_mean`, `null_same_stance_fraction_sd`, `null_same_stance_fraction_q025`, `null_same_stance_fraction_q975`, `null_mean_abs_distance_mean`, `null_mean_abs_distance_sd`, `null_mean_abs_distance_q025`, `null_mean_abs_distance_q975`, `null_assortativity_mean`, `null_assortativity_sd`, `null_assortativity_q025`, `null_assortativity_q975`

## B2_realized_exposure_homophily.csv.gz

`topic_key`, `matched_seed`, `cell_id`, `run_id`, `cohort`, `horizon`, `identity_condition`, `network_condition`, `round`, `n_slots`, `mean_feed_stance`, `same_stance_fraction`, `mean_abs_distance`, `pooled_slot_stance_entropy_nats`, `mean_event_feed_entropy_nats`, `same_group_fraction`, `blue_source_fraction`, `green_source_fraction`, `repeated_post_within_receiver_slots`, `repeated_post_within_receiver_fraction`, `repeated_post_across_receivers_slots`, `repeated_post_across_receivers_fraction`, `old_post_repeated_within_receiver_slots`, `old_post_repeated_within_receiver_fraction`, `old_post_repeated_across_receivers_slots`, `old_post_repeated_across_receivers_fraction`, `repeated_source_within_receiver_slots`, `repeated_source_within_receiver_fraction`, `same_stance_slots`, `distance_sum`, `event_entropy_sum`, `n_events_with_feed`, `same_group_slots`, `blue_source_slots`, `green_source_slots`, `mean_age_rounds`, `fraction_age_ge_1`, `fraction_age_ge_5`, `fraction_age_ge_10`, `post_identity_basis`

## B3_identity_effects_by_seed.csv.gz

`topic_key`, `matched_seed`, `cohort`, `horizon`, `round`, `network_condition`, `a0_run_id`, `a1_run_id`, `variance_a1_minus_a0`, `mean_a1_minus_a0`, `share_1_a1_minus_a0`, `share_2_a1_minus_a0`, `share_3_a1_minus_a0`, `share_4_a1_minus_a0`, `share_5_a1_minus_a0`, `share_6_a1_minus_a0`, `share_7_a1_minus_a0`, `change_event_rate_a1_minus_a0`, `n_low_to_high_a1_minus_a0`, `n_high_to_low_a1_minus_a0`, `low_to_high_event_rate_a1_minus_a0`, `high_to_low_event_rate_a1_minus_a0`, `upward_event_rate_a1_minus_a0`, `downward_event_rate_a1_minus_a0`, `excess_same_stance_unrestricted_a1_minus_a0`, `excess_same_stance_within_group_a1_minus_a0`, `variance_a0`, `mean_a0`, `share_1_a0`, `share_2_a0`, `share_3_a0`, `share_4_a0`, `share_5_a0`, `share_6_a0`, `share_7_a0`, `change_event_rate_a0`, `n_low_to_high_a0`, `n_high_to_low_a0`, `low_to_high_event_rate_a0`, `high_to_low_event_rate_a0`, `upward_event_rate_a0`, `downward_event_rate_a0`, `excess_same_stance_unrestricted_a0`, `excess_same_stance_within_group_a0`, `variance_a1`, `mean_a1`, `share_1_a1`, `share_2_a1`, `share_3_a1`, `share_4_a1`, `share_5_a1`, `share_6_a1`, `share_7_a1`, `change_event_rate_a1`, `n_low_to_high_a1`, `n_high_to_low_a1`, `low_to_high_event_rate_a1`, `high_to_low_event_rate_a1`, `upward_event_rate_a1`, `downward_event_rate_a1`, `excess_same_stance_unrestricted_a1`, `excess_same_stance_within_group_a1`, `interpretation`

## B3_identity_network_interactions.csv.gz

`topic_key`, `matched_seed`, `cohort`, `horizon`, `round`, `network_condition`, `contrast_type`, `variance_did`, `mean_did`, `share_1_did`, `share_2_did`, `share_3_did`, `share_4_did`, `share_5_did`, `share_6_did`, `share_7_did`, `change_event_rate_did`, `n_low_to_high_did`, `n_high_to_low_did`, `low_to_high_event_rate_did`, `high_to_low_event_rate_did`, `upward_event_rate_did`, `downward_event_rate_did`, `excess_same_stance_unrestricted_did`, `excess_same_stance_within_group_did`, `edge_did_status`

## B3_source_conditional_updating.csv.gz

`topic_key`, `matched_seed`, `cell_id`, `run_id`, `cohort`, `horizon`, `identity_condition`, `network_condition`, `round`, `current_stance`, `n_feed`, `n_same_group_feed`, `n_other_group_feed`, `source_group_mix`, `has_same_stance_source`, `has_opposite_side_source`, `has_different_stance_source`, `feed_mean_stance`, `abs_feed_mean_distance`, `n_events`, `n_changed`, `n_move_toward_feed`, `n_upward`, `n_downward`, `n_reason_change_known`, `n_reason_changed`, `change_rate`, `reason_change_rate`, `move_toward_feed_rate`, `interpretation`

## B4_private_public_distributions.csv.gz

`topic_key`, `matched_seed`, `cell_id`, `run_id`, `cohort`, `horizon`, `identity_condition`, `network_condition`, `round`, `layer`, `n`, `mean`, `variance`, `count_1`, `count_2`, `count_3`, `count_4`, `count_5`, `count_6`, `count_7`, `share_1`, `share_2`, `share_3`, `share_4`, `share_5`, `share_6`, `share_7`

## B4_public_stock_age.csv.gz

`topic_key`, `matched_seed`, `cell_id`, `run_id`, `cohort`, `horizon`, `identity_condition`, `network_condition`, `round`, `n`, `mean_age_rounds`, `fraction_age_ge_1`, `fraction_age_ge_5`, `fraction_age_ge_10`

## B4_realized_exposure_distributions.csv.gz

`topic_key`, `matched_seed`, `cell_id`, `run_id`, `cohort`, `horizon`, `identity_condition`, `network_condition`, `round`, `n`, `mean`, `variance`, `count_1`, `count_2`, `count_3`, `count_4`, `count_5`, `count_6`, `count_7`, `share_1`, `share_2`, `share_3`, `share_4`, `share_5`, `share_6`, `share_7`, `mean_age_rounds`, `fraction_age_ge_1`, `fraction_age_ge_5`, `fraction_age_ge_10`, `repeated_post_within_receiver_slots`, `repeated_post_within_receiver_fraction`, `repeated_post_across_receivers_slots`, `repeated_post_across_receivers_fraction`, `old_post_repeated_within_receiver_slots`, `old_post_repeated_within_receiver_fraction`, `old_post_repeated_across_receivers_slots`, `old_post_repeated_across_receivers_fraction`, `repeated_source_within_receiver_slots`, `repeated_source_within_receiver_fraction`, `post_identity_basis`

## B4_visibility_gap_by_round.csv.gz

`topic_key`, `matched_seed`, `cell_id`, `run_id`, `cohort`, `horizon`, `identity_condition`, `network_condition`, `round`, `mean_agent_private_public_abs_gap`, `private_stock_tv`, `private_stock_wasserstein`, `stock_before_after_round_tv`, `n_stock_agents_replaced_this_round`, `n_new_public_posts`, `interpretation`

## A2_reason_case_index.csv

`case_id`, `run_id`, `ordinal`, `topic_key`, `matched_seed`, `identity_a`, `network_b`, `reason_change_status`, `selection_order`

## A3_candidate_cases.csv

`topic_key`, `matched_seed`, `cell_id`, `run_id`, `cohort`, `horizon`, `identity_a`, `network_b`, `n_agents`, `ordinal`, `round`, `agent_id`, `prior_stance`, `after_stance`, `public_before`, `public_after`, `published`, `reason_changed`, `feed_length`, `exposure_class`, `feed_mean`, `feed_variance`, `distance_numerator`, `distance_denominator`, `same_group_count`, `other_group_count`, `mean_post_age`, `repeat_post_slots`, `prior_source_exposures`, `feed_stance_1_count`, `feed_stance_2_count`, `feed_stance_3_count`, `feed_stance_4_count`, `feed_stance_5_count`, `feed_stance_6_count`, `feed_stance_7_count`, `update_status`, `dominant_feed_stance`, `dominance_relation`, `reason_change_status`, `selection_seed`, `selection_method`, `coder_assessment`, `case_id`, `selection_order`

## A3_mechanism_evidence_matrix.csv

`case_id`, `run_id`, `ordinal`, `category_id`, `category_name`, `coder_assessment`, `evidence_status`, `required_evidence`, `counterexplanations`, `mechanism_claim`
