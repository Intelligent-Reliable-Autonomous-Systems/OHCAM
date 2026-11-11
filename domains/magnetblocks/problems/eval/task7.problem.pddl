(define (problem blocksworld-pick-place-task7)
(:domain blocksworld-pick-place)
(:objects
    blue_block yellow_block red_block green_block - block
    table_0 - table
    loc_00 loc_01 loc_02 loc_10 loc_11 loc_12 loc_20 loc_21 loc_22 loc_30 loc_31 loc_32 - location)
(:init
    ; stack 1
    (on yellow_block table_0)
    (at-loc yellow_block loc_10)
    (obstructed-above loc_00)
    ; stack 2
    (on red_block table_0)
    (at-loc red_block loc_11)
    (obstructed-above loc_01)
    ; stack 3
    (on green_block table_0) (on blue_block green_block)
    (at-loc green_block loc_12) (at-loc blue_block loc_22)
    (obstructed-above loc_02) (obstructed-above loc_12)

    ; block attributes
    (wooden green_block) (wooden yellow_block)
    (plastic red_block) (plastic blue_block)

    ; location relations
    (loc-above loc_10 loc_00) (loc-above loc_20 loc_10) (loc-above loc_30 loc_20)
    (loc-above loc_11 loc_01) (loc-above loc_21 loc_11) (loc-above loc_31 loc_21)
    (loc-above loc_12 loc_02) (loc-above loc_22 loc_12) (loc-above loc_32 loc_22)

    ; table occupies bottom row
    (at-loc table_0 loc_00) (at-loc table_0 loc_01) (at-loc table_0 loc_02)
)
(:goal
    ; "Stack the green block on the yellow block and the blue block on the green block"
    (and
        (on yellow_block table_0)
        (on green_block yellow_block)
        (on blue_block green_block)
    )
)
)
