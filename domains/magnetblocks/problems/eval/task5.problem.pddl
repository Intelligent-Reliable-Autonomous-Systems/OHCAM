(define (problem blocksworld-pick-place-task5)
(:domain blocksworld-pick-place)
(:objects
    blue_block yellow_block red_block green_block - block
    table_0 - table
    loc_00 loc_01 loc_02 loc_03 loc_04 loc_10 loc_11 loc_12 loc_13 loc_14 loc_20 loc_21 loc_22 loc_23 loc_24 loc_30 loc_31 loc_32 loc_33 loc_34 - location)
(:init
    ; stack 1
    (on red_block table_0) (on blue_block red_block)
    (at-loc red_block loc_11) (at-loc blue_block loc_21)
    (obstructed-above loc_01) (obstructed-above loc_11)
    ; stack 2
    (on green_block table_0) (on yellow_block green_block)
    (at-loc green_block loc_13) (at-loc yellow_block loc_23)
    (obstructed-above loc_03) (obstructed-above loc_13)

    ; block attributes
    (wooden green_block) (wooden yellow_block)
    (plastic red_block) (plastic blue_block)

    ; location relations
    (loc-above loc_10 loc_00) (loc-above loc_20 loc_10) (loc-above loc_30 loc_20)
    (loc-above loc_11 loc_01) (loc-above loc_21 loc_11) (loc-above loc_31 loc_21)
    (loc-above loc_12 loc_02) (loc-above loc_22 loc_12) (loc-above loc_32 loc_22)
    (loc-above loc_13 loc_03) (loc-above loc_23 loc_13) (loc-above loc_33 loc_23)
    (loc-above loc_14 loc_04) (loc-above loc_24 loc_14) (loc-above loc_34 loc_24)

    ; table occupies bottom row
    (at-loc table_0 loc_00) (at-loc table_0 loc_01) (at-loc table_0 loc_02) (at-loc table_0 loc_03) (at-loc table_0 loc_04)
)
(:goal
    ; "Switch the locations of the stacks"
    (and
        (at-loc green_block loc_11)
        (at-loc red_block loc_13)
        (on yellow_block green_block)
        (on blue_block red_block)
    )
)
)
