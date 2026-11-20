hms_standing_poll:
.LFB153:
	.loc 11 716 0
	.cfi_startproc
.LVL1023:
	push r2
.LCFI631:
	.cfi_def_cfa_offset 3
	.cfi_offset 2, -2
	push r3
.LCFI632:
	.cfi_def_cfa_offset 4
	.cfi_offset 3, -3
	push r4
.LCFI633:
	.cfi_def_cfa_offset 5
	.cfi_offset 4, -4
	push r5
.LCFI634:
	.cfi_def_cfa_offset 6
	.cfi_offset 5, -5
	push r6
.LCFI635:
	.cfi_def_cfa_offset 7
	.cfi_offset 6, -6
	push r7
.LCFI636:
	.cfi_def_cfa_offset 8
	.cfi_offset 7, -7
	push r8
.LCFI637:
	.cfi_def_cfa_offset 9
	.cfi_offset 8, -8
	push r9
.LCFI638:
	.cfi_def_cfa_offset 10
	.cfi_offset 9, -9
	push r10
.LCFI639:
	.cfi_def_cfa_offset 11
	.cfi_offset 10, -10
	push r11
.LCFI640:
	.cfi_def_cfa_offset 12
	.cfi_offset 11, -11
	push r12
.LCFI641:
	.cfi_def_cfa_offset 13
	.cfi_offset 12, -12
	push r13
.LCFI642:
	.cfi_def_cfa_offset 14
	.cfi_offset 13, -13
	push r14
.LCFI643:
	.cfi_def_cfa_offset 15
	.cfi_offset 14, -14
	push r15
.LCFI644:
	.cfi_def_cfa_offset 16
	.cfi_offset 15, -15
	push r16
.LCFI645:
	.cfi_def_cfa_offset 17
	.cfi_offset 16, -16
	push r17
.LCFI646:
	.cfi_def_cfa_offset 18
	.cfi_offset 17, -17
	push r28
.LCFI647:
	.cfi_def_cfa_offset 19
	.cfi_offset 28, -18
	push r29
.LCFI648:
	.cfi_def_cfa_offset 20
	.cfi_offset 29, -19
	in r28,__SP_L__
	in r29,__SP_H__
.LCFI649:
	.cfi_def_cfa_register 28
	subi r28,100
	sbc r29,__zero_reg__
.LCFI650:
	.cfi_def_cfa_offset 120
	in __tmp_reg__,__SREG__
	cli
	out __SP_H__,r29
	out __SREG__,__tmp_reg__
	out __SP_L__,r28
/* prologue: function */
/* frame size = 100 */
/* stack size = 118 */
.L__stack_usage = 118
	.loc 11 718 0
	sbiw r24,0
	brne .+2
	rjmp .L792
	movw r16,r24
	subi r16,-128
	sbci r17,-1
	std Y+52,r17
	std Y+51,r16
	movw r26,r16
	ld r30,X+
	ld r31,X
	sbiw r30,0
	brne .+2
	rjmp .L792
	ldd r18,Z+2
	ldd r19,Z+3
	cp r18,r24
	cpc r19,r25
	breq .+2
	rjmp .L792
	subi r30,-116
	sbci r31,-1
	ld r18,Z
	cpse r18,__zero_reg__
	rjmp .L792
.LVL1024:
	movw r30,r24
	ldd r18,Z+4
	cpi r18,lo8(2)
	breq .+2
	rjmp .L792
	movw r8,r24
	.loc 11 719 0
	call synchronize
.LVL1025:
	.loc 11 720 0
	subi r16,28
	sbc r17,__zero_reg__
	movw r26,r16
	ld r24,X+
	ld r25,X
	eor r25,r24
	eor r24,r25
	eor r25,r24
	sbrs r25,0
	rjmp .L794
.LVL1026:
.LBB727:
.LBB728:
	.loc 11 668 0
	movw r24,r8
	subi r24,-65
	sbci r25,-1
	call r64
.LVL1027:
	movw r2,r18
	movw r4,r20
	movw r6,r22
	std Y+41,r24
	std Y+49,r25
.LVL1028:
	.loc 11 670 0
	movw r30,r8
	subi r30,-97
	sbci r31,-1
	ld r25,Z
.LVL1029:
	sbiw r30,1
	ld r24,Z
.LVL1030:
	cp r25,r24
	brne .+2
	rjmp .L792
	.loc 11 669 0
	adiw r30,9
	ld r27,Z
	std Y+33,r27
	.loc 11 670 0
	cpi r27,lo8(4)
	brne .+2
	rjmp .L792
	.loc 11 668 0
	ldd r26,Y+51
	ldd r27,Y+52
	ld r30,X+
	ld r31,X
	ldd r27,Z+12
	std Y+51,r27
	ldd r10,Z+13
	std Y+53,r10
	ldd r11,Z+14
	std Y+63,r11
	ldd r12,Z+15
	adiw r28,75-63
	std Y+63,r12
	sbiw r28,75-63
	ldd r13,Z+16
	adiw r28,76-63
	std Y+63,r13
	sbiw r28,76-63
	ldd r14,Z+17
	adiw r28,77-63
	std Y+63,r14
	sbiw r28,77-63
	ldd r15,Z+18
	adiw r28,78-63
	std Y+63,r15
	sbiw r28,78-63
	ldd r16,Z+19
	std Y+55,r16
	.loc 11 671 0
	movw r18,r2
	movw r20,r4
	movw r22,r6
	ldd r24,Y+41
	ldd r25,Y+49
	ldi r26,lo8(-1)
	call __cmpdi2_s8
	breq .L795
	mov r18,r27
	mov r19,r10
	mov r20,r11
	mov r21,r12
	mov r22,r13
	mov r23,r14
	mov r24,r15
	mov r25,r16
	movw r10,r2
	movw r12,r4
	movw r14,r6
	ldd r16,Y+41
	ldd r17,Y+49
	call __cmpdi2
	brlo .L795
.LVL1031:
.L801:
	.loc 11 687 0
	ldi r22,lo8(16)
	ldi r23,0
	rjmp .L981
.LVL1032:
.L795:
	.loc 11 672 0
	ldd r27,Y+33
	cpi r27,lo8(1)
	breq .+2
	rjmp .L797
	.loc 11 673 0
	movw r30,r8
	subi r30,-105
	sbci r31,-1
	std Y+34,r31
	std Y+33,r30
	ldi r24,lo8(2)
	st Z,r24
.LVL1033:
	ldi r22,0
	ldi r23,lo8(2)
	movw r24,r8
	call add_flags
.LVL1034:
	.loc 11 674 0
	movw r16,r28
	subi r16,-1
	sbci r17,-1
	movw r10,r16
	movw r12,r2
	movw r14,r4
	movw r16,r6
	ldd r18,Y+41
	ldd r19,Y+49
	ldi r20,0
	ldi r22,lo8(3)
	movw r24,r8
	call driver
.LVL1035:
	.loc 11 675 0
	movw r30,r8
	subi r30,-128
	sbci r31,-1
	ld r16,Z
	ldd r17,Z+1
	movw r30,r16
	subi r30,-74
	sbci r31,-1
	ld r24,Z
	sbrs r24,4
	rjmp .L798
	movw r18,r2
	movw r20,r4
	movw r22,r6
	ldd r24,Y+41
	ldd r25,Y+49
	ldi r26,lo8(-1)
	call __cmpdi2_s8
	brne .+2
	rjmp .L798
	.loc 11 676 0
	movw r26,r16
	adiw r26,12
	ld r27,X
	adiw r28,67-63
	std Y+63,r27
	sbiw r28,67-63
	movw r30,r16
	ldd r31,Z+13
	adiw r28,79-63
	std Y+63,r31
	sbiw r28,79-63
	movw r26,r16
	adiw r26,14
	ld r27,X
	adiw r28,87-63
	std Y+63,r27
	sbiw r28,87-63
	movw r30,r16
	ldd r31,Z+15
	adiw r28,91-63
	std Y+63,r31
	sbiw r28,91-63
	movw r26,r16
	adiw r26,16
	ld r30,X
	sbiw r26,16
	adiw r26,17
	ld r31,X
	sbiw r26,17
	adiw r26,18
	ld r27,X
	adiw r28,93-63
	std Y+63,r27
	sbiw r28,93-63
	movw r26,r16
	adiw r26,19
	ld r27,X
	adiw r28,94-63
	std Y+63,r27
	sbiw r28,94-63
	.loc 11 675 0
	adiw r28,67-63
	ldd r10,Y+63
	sbiw r28,67-63
	adiw r28,79-63
	ldd r11,Y+63
	sbiw r28,79-63
	adiw r28,87-63
	ldd r12,Y+63
	sbiw r28,87-63
	adiw r28,91-63
	ldd r13,Y+63
	sbiw r28,91-63
	movw r14,r30
	adiw r28,93-63
	ldd r16,Y+63
	sbiw r28,93-63
	mov r17,r27
	call __cmpdi2
	breq .L798
	brlo .L798
	.loc 11 676 0
	push r25
	ldd r10,Y+41
	push r10
	push r7
	push r6
	push r5
	push r4
	push r3
	push r2
	push r27
	adiw r28,93-63
	ldd r26,Y+63
	sbiw r28,93-63
	push r26
	push r31
	push r30
	adiw r28,91-63
	ldd r27,Y+63
	sbiw r28,91-63
	push r27
	adiw r28,87-63
	ldd r30,Y+63
	sbiw r28,87-63
	push r30
	adiw r28,79-63
	ldd r31,Y+63
	sbiw r28,79-63
	push r31
	adiw r28,67-63
	ldd r26,Y+63
	sbiw r28,67-63
	push r26
	ldd r14,Y+51
	ldd r15,Y+53
	ldd r16,Y+63
	adiw r28,75-63
	ldd r17,Y+63
	sbiw r28,75-63
	adiw r28,76-63
	ldd r18,Y+63
	sbiw r28,76-63
	adiw r28,77-63
	ldd r19,Y+63
	sbiw r28,77-63
	adiw r28,78-63
	ldd r20,Y+63
	sbiw r28,78-63
	ldd r21,Y+55
	ldi r22,0
	movw r24,r28
	adiw r24,1
	call dispatch_report
.LVL1036:
	in __tmp_reg__,__SREG__
	cli
	out __SP_H__,r29
	out __SREG__,__tmp_reg__
	out __SP_L__,r28
	cpse r24,__zero_reg__
	rjmp .L799
.LVL1037:
.L798:
	.loc 11 677 0
	ldi r22,lo8(13)
	ldi r23,0
.L981:
	movw r24,r8
	call unknown
.LVL1038:
.L982:
	movw r30,r8
	subi r30,-105
	sbci r31,-1
	ldi r24,lo8(4)
.LVL1039:
.L978:
.LBE728:
.LBE727:
	.loc 11 740 0
	st Z,r24
	rjmp .L792
.LVL1040:
.L799:
.LBB736:
.LBB733:
	.loc 11 682 0
	movw r24,r28
	adiw r24,21
	call r64
.LVL1041:
	movw r16,r18
	movw r18,r20
	movw r20,r22
	movw r22,r24
	movw r24,r8
	subi r24,-73
	sbci r25,-1
	call w64
.LVL1042:
	ldi r24,lo8(3)
	ldd r26,Y+33
	ldd r27,Y+34
	st X,r24
.LVL1043:
.L792:
/* epilogue start */
.LBE733:
.LBE736:
	.loc 11 749 0
	subi r28,-100
	sbci r29,-1
	in __tmp_reg__,__SREG__
	cli
	out __SP_H__,r29
	out __SREG__,__tmp_reg__
	out __SP_L__,r28
	pop r29
	pop r28
	pop r17
	pop r16
	pop r15
	pop r14
	pop r13
	pop r12
	pop r11
	pop r10
	pop r9
	pop r8
	pop r7
	pop r6
	pop r5
	pop r4
	pop r3
	pop r2
	ret
.LVL1044:
.L797:
.LBB737:
.LBB734:
	.loc 11 684 0
	ldd r27,Y+33
	cpi r27,lo8(3)
	brne .L792
	.loc 11 685 0
	movw r30,r28
	adiw r30,1
	movw r10,r30
	movw r12,r2
	movw r14,r4
	movw r16,r6
	ldd r18,Y+41
	ldd r19,Y+49
	ldi r20,0
	ldi r22,lo8(4)
	movw r24,r8
	call driver
.LVL1045:
	.loc 11 686 0
	movw r30,r8
	subi r30,-128
	sbci r31,-1
	ld r10,Z
	ldd r11,Z+1
	std Y+34,r11
	std Y+33,r10
	movw r30,r10
	subi r30,-74
	sbci r31,-1
	ld r24,Z
	sbrs r24,4
	rjmp .L982
	.loc 11 687 0
	movw r18,r2
	movw r20,r4
	movw r22,r6
	ldd r24,Y+41
	ldd r25,Y+49
	ldi r26,lo8(-1)
	call __cmpdi2_s8
	brne .+2
	rjmp .L801
	ldd r26,Y+33
	ldd r27,Y+34
	adiw r26,12
	ld r27,X
	std Y+51,r27
	ldd r30,Y+33
	ldd r31,Y+34
	ldd r31,Z+13
	std Y+53,r31
	ldd r26,Y+33
	ldd r27,Y+34
	adiw r26,14
	ld r27,X
	std Y+63,r27
	ldd r30,Y+33
	ldd r31,Y+34
	ldd r31,Z+15
	adiw r28,75-63
	std Y+63,r31
	sbiw r28,75-63
	ldd r26,Y+33
	ldd r27,Y+34
	adiw r26,16
	ld r27,X
	adiw r28,76-63
	std Y+63,r27
	sbiw r28,76-63
	ldd r30,Y+33
	ldd r31,Y+34
	ldd r31,Z+17
	adiw r28,77-63
	std Y+63,r31
	sbiw r28,77-63
	ldd r26,Y+33
	ldd r27,Y+34
	adiw r26,18
	ld r27,X
	adiw r28,78-63
	std Y+63,r27
	sbiw r28,78-63
	ldd r30,Y+33
	ldd r31,Y+34
	ldd r31,Z+19
	std Y+55,r31
	ldd r10,Y+51
	ldd r11,Y+53
	ldd r12,Y+63
	adiw r28,75-63
	ldd r13,Y+63
	sbiw r28,75-63
	adiw r28,76-63
	ldd r14,Y+63
	sbiw r28,76-63
	adiw r28,77-63
	ldd r15,Y+63
	sbiw r28,77-63
	mov r16,r27
	mov r17,r31
	call __cmpdi2
	breq .+2
	brsh .+2
	rjmp .L801
	.loc 11 688 0
	ldd r17,Y+1
	tst r17
	brne .+2
	rjmp .L792
	.loc 11 690 0
	movw r24,r28
	adiw r24,1
	call report_reserved
.LVL1046:
	tst r24
	brne .+2
	rjmp .L798
	cpi r17,lo8(3)
	breq .+2
	rjmp .L798
	.loc 11 691 0
	ldd r24,Y+2
	cpi r24,lo8(1)
	breq .+2
	rjmp .L798
	ldd r24,Y+3
	cpi r24,lo8(1)
	breq .+2
	rjmp .L798
	ldd r24,Y+6
	cpi r24,lo8(1)
	breq .+2
	rjmp .L798
	.loc 11 692 0
	movw r22,r28
	subi r22,-1
	sbci r23,-1
	ldd r24,Y+33
	ldd r25,Y+34
	call evidence_ok.isra.3
.LVL1047:
	.loc 11 691 0
	tst r24
	brne .+2
	rjmp .L798
	.loc 11 692 0
	ldd r24,Y+7
	cpse r24,__zero_reg__
	rjmp .L798
	ldd r24,Y+8
	cpse r24,__zero_reg__
	rjmp .L798
	ldd r25,Y+9
	movw r30,r8
	subi r30,-96
	sbci r31,-1
	ld r24,Z
	cpse r25,r24
	rjmp .L798
	.loc 11 693 0
	movw r24,r28
	adiw r24,13
	call r32
.LVL1048:
	movw r12,r22
	movw r14,r24
	movw r24,r8
	subi r24,-85
	sbci r25,-1
	call r32
.LVL1049:
	cp r12,r22
	cpc r13,r23
	cpc r14,r24
	cpc r15,r25
	breq .+2
	rjmp .L798
	.loc 11 694 0
	movw r24,r28
	adiw r24,17
	call r32
.LVL1050:
	movw r12,r22
	movw r14,r24
	movw r30,r8
	subi r30,124
	sbci r31,-1
	ld r4,Z
	ldd r5,Z+1
.LVL1051:
	movw r24,r4
	subi r24,100
	sbci r25,-1
	call r32
.LVL1052:
	.loc 11 693 0
	cp r22,r12
	cpc r23,r13
	cpc r24,r14
	cpc r25,r15
	brlo .+2
	rjmp .L798
	.loc 11 695 0
	movw r16,r8
	subi r16,-73
	sbci r17,-1
	std Y+50,r17
	std Y+49,r16
	movw r24,r16
	call r64
.LVL1053:
	.loc 11 694 0
	ldi r26,lo8(-1)
	call __cmpdi2_s8
	brne .+2
	rjmp .L798
	.loc 11 695 0
	ldi r20,lo8(8)
	ldi r21,0
	movw r22,r16
	movw r24,r28
	adiw r24,21
	call memcmp
.LVL1054:
	cp __zero_reg__,r24
	cpc __zero_reg__,r25
	brlt .+2
	rjmp .L798
	.loc 11 696 0
	movw r24,r28
	adiw r24,21
	call r64
.LVL1055:
	mov r27,r18
	mov r26,r19
	mov r31,r20
	mov r30,r21
	movw r2,r22
	mov r7,r24
	mov r6,r25
	.loc 11 695 0
	ldd r18,Y+51
	ldd r19,Y+53
	ldd r20,Y+63
	adiw r28,75-63
	ldd r21,Y+63
	sbiw r28,75-63
	adiw r28,76-63
	ldd r22,Y+63
	sbiw r28,76-63
	adiw r28,77-63
	ldd r23,Y+63
	sbiw r28,77-63
	adiw r28,78-63
	ldd r24,Y+63
	sbiw r28,78-63
	ldd r25,Y+55
	mov r10,r27
	mov r11,r26
	mov r12,r31
	mov r13,r30
	movw r14,r2
	mov r16,r7
	mov r17,r6
	call __cmpdi2
	brsh .+2
	rjmp .L798
	.loc 11 697 0
	call __subdi3
	movw r30,r4
	subi r30,-84
	sbci r31,-1
	ld r2,Z
	ldd r3,Z+1
	eor r3,r2
	eor r2,r3
	eor r3,r2
	movw r10,r2
	mov r13,__zero_reg__
	mov r12,__zero_reg__
	mov r14,__zero_reg__
	mov r15,__zero_reg__
	movw r16,r14
	std Y+41,r10
	std Y+42,r11
	std Y+43,r12
	std Y+44,r13
	std Y+45,r14
	std Y+46,r15
	std Y+47,r16
	std Y+48,r17
	.loc 11 696 0
	mov r12,__zero_reg__
	mov r13,__zero_reg__
	mov r14,__zero_reg__
	mov r15,__zero_reg__
	ldi r16,0
	ldi r17,0
	call __cmpdi2
	brlo .+2
	rjmp .L798
.LVL1056:
.LBB729:
.LBB730:
	.loc 11 32 0
	movw r24,r28
	adiw r24,29
	call r32
.LVL1057:
.LBE730:
.LBE729:
	.loc 11 697 0
	or r22,r23
	or r22,r24
	or r22,r25
	breq .+2
	rjmp .L798
	.loc 11 700 0
	ldi r24,lo8(1)
	movw r30,r8
	subi r30,-106
	sbci r31,-1
	st Z,r24
	adiw r30,1
	st Z,r24
	.loc 11 701 0
	ldd r24,Y+4
	adiw r30,1
	st Z,r24
	ldd r24,Y+5
	adiw r30,1
	st Z,r24
	.loc 11 702 0
	ldi r24,lo8(4)
	movw r30,r28
	adiw r30,17
	movw r26,r8
	subi r26,-110
	sbci r27,-1
	0:
	ld r0,Z+
	st X+,r0
	dec r24
	brne 0b
	ldi r24,lo8(8)
	movw r30,r28
	adiw r30,21
	movw r26,r8
	subi r26,-114
	sbci r27,-1
	0:
	ld r0,Z+
	st X+,r0
	dec r24
	brne 0b
	.loc 11 703 0
	ldi r24,lo8(4)
	movw r30,r28
	adiw r30,29
	movw r26,r8
	subi r26,-122
	sbci r27,-1
	0:
	ld r0,Z+
	st X+,r0
	dec r24
	brne 0b
	movw r30,r8
	subi r30,-126
	sbci r31,-1
	st Z,__zero_reg__
	adiw r30,1
	st Z,__zero_reg__
	.loc 11 706 0
	movw r30,r4
	subi r30,-116
	sbci r31,-1
	ld r24,Z
	tst r24
	brne .+2
	rjmp .L805
.LBB731:
	.loc 11 707 0
	ldd r26,Y+33
	ldd r27,Y+34
	adiw r26,12
	ld r27,X
	std Y+41,r27
	ldd r30,Y+33
	ldd r31,Y+34
	ldd r31,Z+13
	std Y+51,r31
	ldd r26,Y+33
	ldd r27,Y+34
	adiw r26,14
	ld r6,X
	sbiw r26,14
	adiw r26,15
	ld r7,X
	sbiw r26,15
	adiw r26,16
	ld r27,X
	std Y+53,r27
	ldd r30,Y+33
	ldd r31,Y+34
	ldd r31,Z+17
	std Y+63,r31
	ldd r26,Y+33
	ldd r27,Y+34
	adiw r26,18
	ld r3,X
	sbiw r26,18
	adiw r26,19
	ld r2,X
	movw r24,r4
	subi r24,-96
	sbci r25,-1
	call r64
.LVL1058:
	mov r27,r18
	mov r26,r19
	mov r31,r20
	mov r30,r21
	adiw r28,75-63
	std Y+63,r22
	sbiw r28,75-63
	adiw r28,76-63
	std Y+63,r23
	sbiw r28,76-63
	adiw r28,77-63
	std Y+63,r24
	sbiw r28,77-63
	adiw r28,78-63
	std Y+63,r25
	sbiw r28,78-63
	ldd r18,Y+41
	ldd r19,Y+51
	movw r20,r6
	ldd r22,Y+53
	ldd r23,Y+63
	mov r24,r3
	mov r25,r2
	mov r10,r27
	mov r11,r26
	mov r12,r31
	mov r13,r30
	adiw r28,75-63
	ldd r14,Y+63
	sbiw r28,75-63
	adiw r28,76-63
	ldd r15,Y+63
	sbiw r28,76-63
	adiw r28,77-63
	ldd r16,Y+63
	sbiw r28,77-63
	adiw r28,78-63
	ldd r17,Y+63
	sbiw r28,78-63
	call __subdi3
	std Y+33,r18
	std Y+34,r19
	std Y+35,r20
	std Y+36,r21
	std Y+37,r22
	std Y+38,r23
	std Y+39,r24
	std Y+40,r25
.LVL1059:
	.loc 11 708 0
	ldd r18,Y+41
	ldd r19,Y+51
	movw r20,r6
	ldd r22,Y+53
	ldd r23,Y+63
	mov r24,r3
	mov r25,r2
	call __cmpdi2
	brlo .L979
	.loc 11 709 0
	movw r2,r8
	ldi r27,89
	add r2,r27
	adc r3,__zero_reg__
	movw r24,r2
	call r32
.LVL1060:
	movw r4,r22
	movw r6,r24
	movw r26,r24
	movw r24,r22
	com r24
	com r25
	com r26
	com r27
	movw r14,r24
	movw r16,r26
	ldi r18,0
	ldi r19,0
	movw r20,r18
	std Y+41,r24
	std Y+42,r15
	std Y+43,r26
	std Y+44,r17
	std Y+45,r18
	std Y+46,r19
	std Y+47,r20
	std Y+48,r21
	.loc 11 708 0
	ldd r18,Y+33
	ldd r19,Y+34
	ldd r20,Y+35
	ldd r21,Y+36
	ldd r22,Y+37
	ldd r23,Y+38
	ldd r24,Y+39
	ldd r25,Y+40
	movw r10,r14
	movw r12,r26
	mov r14,__zero_reg__
	mov r15,__zero_reg__
	ldi r16,0
	ldi r17,0
	call __cmpdi2
	breq .L807
	brlo .L807
.LVL1061:
.L979:
.LBE731:
.LBE734:
.LBE737:
	.loc 11 745 0
	ldi r22,lo8(14)
	ldi r23,0
	movw r24,r8
	call unknown
.LVL1062:
	rjmp .L792
.LVL1063:
.L807:
.LBB738:
.LBB735:
.LBB732:
	.loc 11 710 0
	ldd r20,Y+33
	ldd r21,Y+34
	ldd r22,Y+35
	ldd r23,Y+36
	add r20,r4
	adc r21,r5
	adc r22,r6
	adc r23,r7
	movw r24,r2
	call w32
.LVL1064:
.L805:
.LBE732:
	.loc 11 712 0
	ldi r22,lo8(-128)
	ldi r23,0
	movw r24,r8
	call add_flags
.LVL1065:
	movw r30,r8
	subi r30,-97
	sbci r31,-1
	movw r26,r8
	subi r26,-96
	sbci r27,-1
	ld r24,X
	st Z,r24
	.loc 11 713 0
	adiw r30,31
	ld __tmp_reg__,Z+
	ld r31,Z
	mov r30,__tmp_reg__
	ldd r16,Z+12
	ldd r17,Z+13
	ldd r18,Z+14
	ldd r19,Z+15
	ldd r20,Z+16
	ldd r21,Z+17
	ldd r22,Z+18
	ldd r23,Z+19
	ldd r24,Y+49
	ldd r25,Y+50
	call w64
.LVL1066:
	.loc 11 714 0
	movw r30,r8
	subi r30,-93
	sbci r31,-1
	movw r26,r8
	subi r26,-94
	sbci r27,-1
	ld r24,X
	st Z,r24
	movw r24,r8
	call bump
.LVL1067:
	rjmp .L792
.LVL1068:
.L794:
.LBE735:
.LBE738:
	.loc 11 721 0
	movw r24,r8
	adiw r24,9
	call r32
.LVL1069:
	cpi r22,-1
	sbci r23,-1
	sbci r24,-1
	sbci r25,-1
	breq .L808
	movw r24,r8
	adiw r24,5
	call r32
.LVL1070:
	cpi r22,-1
	sbci r23,-1
	sbci r24,-1
	sbci r25,-1
	brne .L809
.L808:
	.loc 11 722 0
	ldi r22,0
	ldi r23,lo8(4)
	movw r24,r8
	call add_flags
.LVL1071:
	ldi r18,lo8(1)
	ldi r20,lo8(5)
	ldi r22,lo8(14)
	ldi r23,0
.L980:
	.loc 11 732 0
	movw r24,r8
	call loss
.LVL1072:
	rjmp .L792
.L809:
	.loc 11 724 0
	movw r14,r8
	ldi r20,93
	add r14,r20
	adc r15,__zero_reg__
	movw r26,r14
	ld r24,X
	subi r24,lo8(-(-1))
	cpi r24,lo8(2)
	brlo .+2
	rjmp .L792
	.loc 11 725 0
	ldi r22,0
	movw r24,r8
	call guarded
.LVL1073:
	adiw r28,78-63
	std Y+63,r24
	sbiw r28,78-63
.LVL1074:
	.loc 11 726 0
	cpse r24,__zero_reg__
	rjmp .L810
	movw r30,r16
	ld r24,Z
	ldd r25,Z+1
.LVL1075:
	eor r25,r24
	eor r24,r25
	eor r25,r24
	sbrs r25,0
	rjmp .L811
.L810:
	.loc 11 727 0
	movw r26,r16
	ld r24,X+
	ld r25,X
	eor r25,r24
	eor r24,r25
	eor r25,r24
	sbrc r25,0
	rjmp .L792
	adiw r28,78-63
	ldd r27,Y+63
	sbiw r28,78-63
	ldi r22,lo8(7)
	ldi r23,0
	cpi r27,lo8(26)
	breq .L812
	ldi r22,lo8(10)
	ldi r23,0
.L812:
	ldi r18,lo8(1)
	ldi r20,lo8(5)
	rjmp .L980
.L811:
	.loc 11 730 0
	movw r30,r14
	ld r24,Z
	cpi r24,lo8(2)
	brne .+2
	rjmp .L813
.L831:
	.loc 11 735 0
	movw r30,r8
	subi r30,-95
	sbci r31,-1
	ld r10,Z
	std Y+33,r10
.LVL1076:
	.loc 11 736 0
	tst r10
	brne .+2
	rjmp .L814
	.loc 11 737 0
	ldd r27,Y+33
	cpi r27,lo8(2)
	brsh .+2
	rjmp .L832
.LVL1077:
.LBB739:
.LBB740:
	.loc 11 656 0
	movw r30,r8
	subi r30,-93
	sbci r31,-1
	ld r24,Z
	cpi r24,lo8(2)
	brne .L849
	adiw r30,11
	ld r24,Z
	cpi r24,lo8(-1)
	brne .L849
	.loc 11 654 0
	adiw r30,28
	ld r4,Z
	ldd r5,Z+1
	.loc 11 656 0
	movw r30,r4
	subi r30,114
	sbci r31,-1
	ld r24,Z
	tst r24
	breq .L849
	.loc 11 654 0
	movw r26,r4
	subi r26,-116
	sbci r27,-1
	ld r17,X
	.loc 11 657 0
	st Z,__zero_reg__
.LVL1078:
	.loc 11 658 0
	ldi r22,0
	movw r24,r8
	call fresh
.LVL1079:
	tst r24
	breq .L851
	ldi r22,lo8(1)
	movw r24,r8
	call fresh
.LVL1080:
	cpse r24,__zero_reg__
	rjmp .L852
.L851:
	ldi r18,lo8(1)
	ldi r20,lo8(5)
	ldi r22,lo8(5)
	ldi r23,0
.LVL1081:
.L976:
.LBB741:
.LBB742:
	.loc 11 627 0
	movw r24,r8
	call loss
.LVL1082:
.L849:
.LBE742:
.LBE741:
.LBE740:
.LBE739:
	.loc 11 743 0
	movw r30,r8
	subi r30,-100
	sbci r31,-1
	ld r24,Z
	ldd r25,Z+1
	eor r25,r24
	eor r24,r25
	eor r25,r24
	sbrc r25,0
	rjmp .L792
	.loc 11 744 0
	sbiw r30,5
	st Z,__zero_reg__
	.loc 11 745 0
	adiw r30,33
	ld __tmp_reg__,Z+
	ld r31,Z
	mov r30,__tmp_reg__
	ldd r27,Z+12
	ldd r26,Z+13
	ldd r10,Z+14
	std Y+41,r10
	ldd r11,Z+15
	std Y+49,r11
	ldd r4,Z+16
	ldd r5,Z+17
	ldd r6,Z+18
	ldd r7,Z+19
	movw r24,r8
	subi r24,124
	sbci r25,-1
	movw r30,r24
	ld r24,Z
	ldd r25,Z+1
	subi r24,-80
	sbci r25,-1
	movw r30,r24
	ld r2,Z
	ldd r3,Z+1
	eor r3,r2
	eor r2,r3
	eor r3,r2
	movw r10,r2
	mov r13,__zero_reg__
	mov r12,__zero_reg__
	mov r14,__zero_reg__
	mov r15,__zero_reg__
	movw r16,r14
	std Y+33,r10
	std Y+34,r11
	std Y+35,r12
	std Y+36,r13
	std Y+37,r14
	std Y+38,r15
	std Y+39,r16
	std Y+40,r17
	com r10
	com r11
	mov r18,r27
	mov r19,r26
	ldd r20,Y+41
	ldd r21,Y+49
	movw r22,r4
	movw r24,r6
	clr r12
	dec r12
	clr r13
	dec r13
	clr r14
	dec r14
	clr r15
	dec r15
	ldi r16,lo8(-1)
	ldi r17,lo8(-1)
	call __cmpdi2
	brlo .+2
	rjmp .L979
	.loc 11 746 0
	ldd r20,Y+41
	ldd r21,Y+49
	movw r22,r4
	movw r24,r6
	ldd r10,Y+33
	ldd r11,Y+34
	mov r12,__zero_reg__
	mov r13,__zero_reg__
	mov r14,__zero_reg__
	mov r15,__zero_reg__
	ldi r16,0
	ldi r17,0
	call __adddi3
	movw r16,r18
	movw r18,r20
	movw r20,r22
	movw r22,r24
	movw r24,r8
	adiw r24,49
	call w64
.LVL1083:
	rjmp .L792
.LVL1084:
.L813:
	.loc 11 731 0
	ldi r22,0
	movw r24,r8
	call fresh
.LVL1085:
	tst r24
	breq .L816
	ldi r22,lo8(1)
	movw r24,r8
	call fresh
.LVL1086:
	cpse r24,__zero_reg__
	rjmp .L817
.L816:
	ldi r18,lo8(1)
	ldi r20,lo8(5)
	ldi r22,lo8(5)
	ldi r23,0
	rjmp .L980
.L817:
	.loc 11 732 0
	ldd r26,Y+51
	ldd r27,Y+52
	ld r30,X+
	ld r31,X
	ldd r14,Z+12
	ldd r15,Z+13
	ldd r16,Z+14
	ldd r17,Z+15
	ldd r18,Z+16
	ldd r19,Z+17
	ldd r20,Z+18
	ldd r21,Z+19
	ldi r22,0
	movw r24,r8
	call account_ok
.LVL1087:
	cpse r24,__zero_reg__
	rjmp .L818
	ldi r18,lo8(1)
	ldi r20,lo8(5)
	ldi r22,lo8(15)
	ldi r23,0
	rjmp .L980
.L818:
.LVL1088:
.LBB773:
.LBB774:
	.loc 11 559 0
	movw r30,r8
	subi r30,-104
	sbci r31,-1
	ld r24,Z
.LVL1089:
	.loc 11 561 0
	cpi r24,lo8(2)
	brlo .+2
	rjmp .L820
	.loc 11 562 0
	movw r16,r8
	subi r16,124
	sbci r17,-1
	std Y+54,r17
	std Y+53,r16
	movw r26,r16
	ld r16,X+
	ld r17,X
	movw r30,r16
	ldi r18,lo8(44)
	mul r24,r18
	add r30,r0
	adc r31,r1
	clr __zero_reg__
	movw r20,r30
	subi r20,88
	sbci r21,-1
	movw r2,r20
.LVL1090:
	movw r22,r16
	subi r22,112
	sbci r23,-1
	std Y+34,r23
	std Y+33,r22
.LVL1091:
	.loc 11 563 0
	ldi r22,lo8(1)
.LVL1092:
	movw r24,r8
.LVL1093:
	call fresh
.LVL1094:
	mov r5,r24
	tst r24
	brne .+2
	rjmp .L821
	movw r6,r2
	ldi r23,4
	add r6,r23
	adc r7,__zero_reg__
	movw r24,r16
	subi r24,108
	sbci r25,-1
	std Y+42,r25
	std Y+41,r24
	ldi r20,lo8(8)
	ldi r21,0
	movw r22,r6
	call memcmp
.LVL1095:
	cp __zero_reg__,r24
	cpc __zero_reg__,r25
	brlt .+2
	rjmp .L883
	movw r26,r16
	subi r26,100
	sbci r27,-1
	std Y+50,r27
	std Y+49,r26
	movw r24,r26
	call r32
.LVL1096:
	movw r12,r22
	movw r14,r24
	movw r10,r2
	ldi r27,22
	add r10,r27
	adc r11,__zero_reg__
	movw r24,r10
	call r32
.LVL1097:
	cp r22,r12
	cpc r23,r13
	cpc r24,r14
	cpc r25,r15
	brlo .+2
	rjmp .L883
	movw r30,r16
	subi r30,90
	sbci r31,-1
	ld r5,Z
	tst r5
	brne .+2
	rjmp .L821
	ldd r24,Y+33
	ldd r25,Y+34
	call r32
.LVL1098:
	movw r12,r22
	movw r14,r24
	.loc 11 564 0
	movw r30,r2
	ldd r24,Z+39
	cpse r24,__zero_reg__
	rjmp .L822
	clr r5
	inc r5
	or r12,r13
	or r12,r14
	or r12,r15
	brne .+2
	rjmp .L824
.L884:
.LBE774:
.LBE773:
	.loc 11 559 0
	mov r5,__zero_reg__
	rjmp .L824
.L822:
.LVL1099:
.LBB792:
.LBB787:
.LBB775:
.LBB776:
	.loc 11 32 0
	movw r24,r16
	subi r24,-76
	sbci r25,-1
.LVL1100:
	call r32
.LVL1101:
.LBE776:
.LBE775:
	.loc 11 565 0
	cp r12,r22
	cpc r13,r23
	cpc r14,r24
	cpc r15,r25
	brlt .L884
.LVL1102:
.LBB777:
.LBB778:
.LBB779:
	.loc 11 32 0
	movw r24,r16
	subi r24,-112
	sbci r25,-1
.LVL1103:
	call r32
.LVL1104:
	movw r12,r22
	movw r14,r24
.LVL1105:
.LBE779:
.LBE778:
.LBB780:
.LBB781:
	movw r24,r16
	subi r24,-120
	sbci r25,-1
.LVL1106:
	call r32
.LVL1107:
.LBE781:
.LBE780:
	.loc 11 568 0
	movw r20,r14
	movw r18,r12
	sub r18,r22
	sbc r19,r23
	sbc r20,r24
	sbc r21,r25
	adiw r28,63-60
	std Y+60,r18
	std Y+61,r19
	std Y+62,r20
	std Y+63,r21
	sbiw r28,63-60
.LVL1108:
.LBB782:
.LBB783:
	.loc 11 32 0
	movw r24,r16
	subi r24,-72
	sbci r25,-1
.LVL1109:
	call r32
.LVL1110:
	movw r12,r22
	movw r14,r24
.LVL1111:
.LBE783:
.LBE782:
.LBE777:
.LBE787:
.LBE792:
	.loc 11 569 0
	clr r5
	inc r5
.LBB793:
.LBB788:
.LBB784:
	cp r12,__zero_reg__
	cpc r13,__zero_reg__
	cpc r14,__zero_reg__
	cpc r15,__zero_reg__
	breq .L824
	.loc 11 570 0
	ldi r22,0
	movw r24,r8
	call fresh
.LVL1112:
	.loc 11 569 0
	tst r24
	breq .L884
	.loc 11 570 0
	ldi r20,lo8(8)
	ldi r21,0
	movw r22,r6
	movw r24,r16
	subi r24,-124
	sbci r25,-1
	call memcmp
.LVL1113:
	cp __zero_reg__,r24
	cpc __zero_reg__,r25
	brlt .+2
	rjmp .L884
	.loc 11 571 0
	movw r24,r16
	subi r24,124
	sbci r25,-1
	call r32
.LVL1114:
	movw r4,r22
	movw r6,r24
	movw r24,r2
	adiw r24,12
	call r32
.LVL1115:
	.loc 11 570 0
	cp r22,r4
	cpc r23,r5
	cpc r24,r6
	cpc r25,r7
	brlo .+2
	rjmp .L884
	.loc 11 571 0
	clr r5
	inc r5
	adiw r28,63-60
	ldd r20,Y+60
	ldd r21,Y+61
	ldd r22,Y+62
	ldd r23,Y+63
	sbiw r28,63-60
	cp r20,r12
	cpc r21,r13
	cpc r22,r14
	cpc r23,r15
	brge .+2
	rjmp .L884
.LVL1116:
.L824:
.LBE784:
	.loc 11 573 0
	ldi r24,lo8(4)
	ldd r30,Y+49
	ldd r31,Y+50
	movw r26,r10
	0:
	ld r0,Z+
	st X+,r0
	dec r24
	brne 0b
	ldi r24,lo8(8)
	ldd r30,Y+41
	ldd r31,Y+42
	movw r26,r2
	adiw r26,26
	0:
	ld r0,Z+
	st X+,r0
	dec r24
	brne 0b
	ldi r24,lo8(4)
	ldd r30,Y+33
	ldd r31,Y+34
	movw r26,r2
	adiw r26,34
	0:
	ld r0,Z+
	st X+,r0
	dec r24
	brne 0b
	.loc 11 574 0
	ldd r26,Y+51
	ldd r27,Y+52
	ld r30,X+
	ld r31,X
	subi r30,18
	sbci r31,-1
	ld r24,Z
	cpse r24,__zero_reg__
	rjmp .L889
.LBE788:
.LBE793:
	ldi r24,lo8(13)
.L827:
.LBB794:
.LBB789:
	movw r30,r2
	std Z+41,r24
	.loc 11 575 0
	movw r30,r16
	subi r30,90
	sbci r31,-1
	st Z,__zero_reg__
.LVL1117:
.L821:
	.loc 11 577 0
	ldd r26,Y+51
	ldd r27,Y+52
	ld r6,X+
	ld r7,X
	ldd r30,Y+53
	ldd r31,Y+54
	ld r24,Z
	ldd r25,Z+1
	subi r24,-104
	sbci r25,-1
	call r64
.LVL1118:
	movw r10,r18
	movw r12,r20
	movw r14,r22
	movw r16,r24
	movw r26,r6
	adiw r26,12
	ld r18,X
	sbiw r26,12
	adiw r26,13
	ld r19,X
	sbiw r26,13
	adiw r26,14
	ld r20,X
	sbiw r26,14
	adiw r26,15
	ld r21,X
	sbiw r26,15
	adiw r26,16
	ld r22,X
	sbiw r26,16
	adiw r26,17
	ld r23,X
	sbiw r26,17
	adiw r26,18
	ld r24,X
	sbiw r26,18
	adiw r26,19
	ld r25,X
	call __cmpdi2
	brsh .L828
	.loc 11 578 0
	tst r5
	breq .L820
	.loc 11 579 0
	movw r30,r6
	subi r30,18
	sbci r31,-1
	ld r24,Z
	tst r24
	breq .L890
.LBE789:
.LBE794:
	ldi r24,lo8(26)
.L830:
.LBB795:
.LBB790:
	movw r30,r2
	std Z+40,r24
	.loc 11 580 0
	ldi r24,lo8(-1)
	movw r30,r8
	subi r30,-104
	sbci r31,-1
	st Z,r24
.LVL1119:
.L820:
.LBE790:
.LBE795:
	.loc 11 733 0
	movw r30,r8
	subi r30,-100
	sbci r31,-1
	ld r24,Z
	ldd r25,Z+1
	eor r25,r24
	eor r24,r25
	eor r25,r24
	sbrc r25,0
	rjmp .L792
	rjmp .L831
.LVL1120:
.L889:
	.loc 11 574 0
	ldi r24,lo8(12)
	rjmp .L827
.LVL1121:
.L883:
	.loc 11 559 0
	mov r5,__zero_reg__
	rjmp .L821
.LVL1122:
.L890:
	.loc 11 579 0
	ldi r24,lo8(10)
	rjmp .L830
.L828:
.LBB796:
.LBB791:
	.loc 11 582 0
	ldi r24,lo8(11)
	movw r26,r2
	adiw r26,40
	st X,r24
	sbiw r26,40
.LVL1123:
.LBB785:
.LBB786:
	.loc 11 35 0
	adiw r26,42
	st X,__zero_reg__
	sbiw r26,42
	ldi r24,lo8(9)
	adiw r26,43
	st X,r24
.LVL1124:
.LBE786:
.LBE785:
	.loc 11 582 0
	ldi r24,lo8(-1)
	movw r30,r8
	subi r30,-104
	sbci r31,-1
	st Z,r24
	.loc 11 583 0
	ldi r18,lo8(1)
	ldi r20,lo8(5)
	ldi r22,lo8(9)
	ldi r23,0
	movw r24,r8
	call loss
.LVL1125:
	rjmp .L820
.LVL1126:
.L814:
.LBE791:
.LBE796:
	.loc 11 736 0
	movw r24,r8
	adiw r24,49
	call r64
.LVL1127:
	movw r10,r18
.LVL1128:
	movw r12,r20
	movw r14,r22
	movw r16,r24
	ldd r26,Y+51
	ldd r27,Y+52
	ld r30,X+
	ld r31,X
	ldd r18,Z+12
	ldd r19,Z+13
	ldd r20,Z+14
	ldd r21,Z+15
	ldd r22,Z+16
	ldd r23,Z+17
	ldd r24,Z+18
	ldd r25,Z+19
	call __cmpdi2
	brsh .+2
	rjmp .L792
.L832:
	.loc 11 738 0
	movw r24,r8
	adiw r24,33
	call r64
.LVL1129:
	movw r30,r28
	adiw r30,1
	movw r10,r30
	movw r12,r18
	movw r14,r20
	movw r16,r22
	movw r18,r24
	ldi r20,0
	ldd r22,Y+33
	movw r24,r8
	call driver
.LVL1130:
	.loc 11 739 0
	movw r30,r8
	subi r30,-100
	sbci r31,-1
	ld r24,Z
	ldd r25,Z+1
	eor r25,r24
	eor r24,r25
	eor r25,r24
	sbrc r25,0
	rjmp .L834
.LVL1131:
.LBB797:
.LBB798:
	.loc 11 522 0
	adiw r30,32
	ld r10,Z
	ldd r11,Z+1
	adiw r28,79-62
	std Y+63,r11
	std Y+62,r10
	sbiw r28,79-62
	movw r24,r10
	ldd r17,Y+33
	ldi r16,lo8(24)
	mul r17,r16
	add r24,r0
	adc r25,r1
	clr __zero_reg__
	movw r18,r24
	subi r18,-120
	sbci r19,-1
	movw r2,r18
.LVL1132:
	.loc 11 523 0
	movw r24,r28
	adiw r24,17
	call r32
.LVL1133:
	std Y+41,r22
	std Y+42,r23
	std Y+43,r24
	std Y+44,r25
.LVL1134:
	movw r20,r2
	subi r20,-12
	sbci r21,-1
	std Y+56,r21
	std Y+55,r20
	movw r24,r20
	call r32
.LVL1135:
	movw r4,r22
	movw r6,r24
.LVL1136:
	.loc 11 524 0
	movw r24,r28
	adiw r24,21
	call r64
.LVL1137:
	std Y+49,r18
	std Y+51,r19
	std Y+53,r20
	std Y+63,r21
	adiw r28,75-63
	std Y+63,r22
	sbiw r28,75-63
	adiw r28,76-63
	std Y+63,r23
	sbiw r28,76-63
	adiw r28,77-63
	std Y+63,r24
	sbiw r28,77-63
	adiw r28,78-63
	std Y+63,r25
	sbiw r28,78-63
.LVL1138:
.LBB799:
.LBB800:
	.loc 11 32 0
	movw r24,r28
.LVL1139:
	adiw r24,29
	call r32
.LVL1140:
	adiw r28,67-60
	std Y+60,r22
	std Y+61,r23
	std Y+62,r24
	std Y+63,r25
	sbiw r28,67-60
.LVL1141:
.LBE800:
.LBE799:
	.loc 11 525 0
	ldd r24,Y+1
	tst r24
	brne .+2
	rjmp .L834
	.loc 11 526 0
	cpi r24,lo8(1)
	brne .L844
	ldd r24,Y+2
	cpse r17,r24
	rjmp .L844
	movw r24,r28
	adiw r24,1
	call report_reserved
.LVL1142:
	tst r24
	breq .L844
	ldd r24,Y+7
	cpse r24,__zero_reg__
	rjmp .L844
	ldd r24,Y+8
	cpse r24,__zero_reg__
	rjmp .L844
	ldd r24,Y+9
	cpse r24,__zero_reg__
	rjmp .L844
	ldd r24,Y+3
	cpi r24,lo8(1)
	brne .L844
	.loc 11 527 0
	ldd r24,Y+6
	cpi r24,lo8(1)
	brne .L844
	movw r30,r8
	subi r30,-128
	sbci r31,-1
	ld r16,Z
	ldd r17,Z+1
	movw r22,r28
	subi r22,-1
	sbci r23,-1
	movw r24,r16
	call evidence_ok.isra.3
.LVL1143:
	cpse r24,__zero_reg__
	rjmp .L836
.L844:
	.loc 11 540 0
	ldi r20,lo8(6)
	ldi r21,0
	rjmp .L975
.LVL1144:
.L836:
	.loc 11 528 0
	movw r24,r28
	adiw r24,13
	call r32
.LVL1145:
	adiw r28,87-60
	std Y+60,r22
	std Y+61,r23
	std Y+62,r24
	std Y+63,r25
	sbiw r28,87-60
	ldd r23,Y+33
	mov r22,r23
	ldi r23,0
	adiw r28,91-62
	std Y+63,r23
	std Y+62,r22
	sbiw r28,91-62
	movw r24,r22
	lsl r24
	rol r25
	lsl r24
	rol r25
	subi r24,-81
	sbci r25,-1
	add r24,r8
	adc r25,r9
	call r32
.LVL1146:
	adiw r28,87-60
	ldd r10,Y+60
	ldd r11,Y+61
	ldd r12,Y+62
	ldd r13,Y+63
	sbiw r28,87-60
	.loc 11 529 0
	ldi r20,lo8(7)
	ldi r21,0
	.loc 11 528 0
	cp r10,r22
	cpc r11,r23
	cpc r12,r24
	cpc r13,r25
	breq .+2
	rjmp .L975
	.loc 11 531 0
	ldd r12,Y+41
	ldd r13,Y+42
	ldd r14,Y+43
	ldd r15,Y+44
	cp r12,__zero_reg__
	cpc r13,__zero_reg__
	cpc r14,__zero_reg__
	cpc r15,__zero_reg__
	breq .L847
	cp r12,r4
	cpc r13,r5
	cpc r14,r6
	cpc r15,r7
	brlo .L847
	cp r4,__zero_reg__
	cpc r5,__zero_reg__
	cpc r6,__zero_reg__
	cpc r7,__zero_reg__
	breq .L839
	cp r4,r12
	cpc r5,r13
	cpc r6,r14
	cpc r7,r15
	brsh .L839
	ldi r18,-1
	cp r4,r18
	cpc r5,r18
	cpc r6,r18
	cpc r7,r18
	breq .L847
	movw r26,r6
	movw r24,r4
	adiw r24,1
	adc r26,__zero_reg__
	adc r27,__zero_reg__
	cp r12,r24
	cpc r13,r25
	cpc r14,r26
	cpc r15,r27
	breq .L839
.LVL1147:
.L847:
	.loc 11 542 0
	ldi r20,lo8(8)
	ldi r21,0
	rjmp .L975
.LVL1148:
.L839:
	.loc 11 534 0
	ldd r18,Y+49
	ldd r19,Y+51
	ldd r20,Y+53
	ldd r21,Y+63
	adiw r28,75-63
	ldd r22,Y+63
	sbiw r28,75-63
	adiw r28,76-63
	ldd r23,Y+63
	sbiw r28,76-63
	adiw r28,77-63
	ldd r24,Y+63
	sbiw r28,77-63
	adiw r28,78-63
	ldd r25,Y+63
	sbiw r28,78-63
	ldi r26,lo8(-1)
	call __cmpdi2_s8
	brne .+2
	rjmp .L840
	movw r26,r16
	adiw r26,12
	ld r27,X
	adiw r28,93-63
	std Y+63,r27
	sbiw r28,93-63
	movw r30,r16
	ldd r31,Z+13
	adiw r28,94-63
	std Y+63,r31
	sbiw r28,94-63
	movw r26,r16
	adiw r26,14
	ld r27,X
	adiw r28,95-63
	std Y+63,r27
	sbiw r28,95-63
	movw r30,r16
	ldd r31,Z+15
	adiw r28,96-63
	std Y+63,r31
	sbiw r28,96-63
	movw r26,r16
	adiw r26,16
	ld r27,X
	adiw r28,97-63
	std Y+63,r27
	sbiw r28,97-63
	movw r30,r16
	ldd r31,Z+17
	adiw r28,98-63
	std Y+63,r31
	sbiw r28,98-63
	movw r26,r16
	adiw r26,18
	ld r27,X
	adiw r28,99-63
	std Y+63,r27
	sbiw r28,99-63
	movw r30,r16
	ldd r31,Z+19
	adiw r28,100-63
	std Y+63,r31
	sbiw r28,100-63
	adiw r28,93-63
	ldd r10,Y+63
	sbiw r28,93-63
	adiw r28,94-63
	ldd r11,Y+63
	sbiw r28,94-63
	adiw r28,95-63
	ldd r12,Y+63
	sbiw r28,95-63
	adiw r28,96-63
	ldd r13,Y+63
	sbiw r28,96-63
	adiw r28,97-63
	ldd r14,Y+63
	sbiw r28,97-63
	adiw r28,98-63
	ldd r15,Y+63
	sbiw r28,98-63
	mov r16,r27
	mov r17,r31
.LVL1149:
	call __cmpdi2
	breq .+4
	brlo .+2
	rjmp .L840
	cp r4,__zero_reg__
	cpc r5,__zero_reg__
	cpc r6,__zero_reg__
	cpc r7,__zero_reg__
	breq .L841
	.loc 11 535 0
	movw r24,r2
	adiw r24,4
	call r64
.LVL1150:
	movw r10,r18
	movw r12,r20
	movw r14,r22
	movw r16,r24
	ldd r18,Y+49
	ldd r19,Y+51
	ldd r20,Y+53
	ldd r21,Y+63
	adiw r28,75-63
	ldd r22,Y+63
	sbiw r28,75-63
	adiw r28,76-63
	ldd r23,Y+63
	sbiw r28,76-63
	adiw r28,77-63
	ldd r24,Y+63
	sbiw r28,77-63
	adiw r28,78-63
	ldd r25,Y+63
	sbiw r28,78-63
	call __cmpdi2
	brsh .+2
	rjmp .L840
.L841:
	.loc 11 536 0
	adiw r28,93-63
	ldd r18,Y+63
	sbiw r28,93-63
	adiw r28,94-63
	ldd r19,Y+63
	sbiw r28,94-63
	adiw r28,95-63
	ldd r20,Y+63
	sbiw r28,95-63
	adiw r28,96-63
	ldd r21,Y+63
	sbiw r28,96-63
	adiw r28,97-63
	ldd r22,Y+63
	sbiw r28,97-63
	adiw r28,98-63
	ldd r23,Y+63
	sbiw r28,98-63
	adiw r28,99-63
	ldd r24,Y+63
	sbiw r28,99-63
	adiw r28,100-63
	ldd r25,Y+63
	sbiw r28,100-63
	ldd r10,Y+49
	ldd r11,Y+51
	ldd r12,Y+53
	ldd r13,Y+63
	adiw r28,75-63
	ldd r14,Y+63
	sbiw r28,75-63
	adiw r28,76-63
	ldd r15,Y+63
	sbiw r28,76-63
	adiw r28,77-63
	ldd r16,Y+63
	sbiw r28,77-63
	adiw r28,78-63
	ldd r17,Y+63
	sbiw r28,78-63
	call __subdi3
	adiw r28,91-62
	ldd r30,Y+62
	ldd r31,Y+63
	sbiw r28,91-62
	adiw r30,9
	lsl r30
	rol r31
	adiw r28,79-62
	ldd r10,Y+62
	ldd r11,Y+63
	sbiw r28,79-62
	add r30,r10
	adc r31,r11
	subi r30,-64
	sbci r31,-1
	ld __tmp_reg__,Z+
	ld r31,Z
	mov r30,__tmp_reg__
	eor r31,r30
	eor r30,r31
	eor r31,r30
	movw r10,r30
	mov r13,__zero_reg__
	mov r12,__zero_reg__
	mov r14,__zero_reg__
	mov r15,__zero_reg__
	movw r16,r14
	adiw r28,79-63
	std Y+63,r10
	sbiw r28,79-63
	adiw r28,80-63
	std Y+63,r11
	sbiw r28,80-63
	adiw r28,81-63
	std Y+63,r12
	sbiw r28,81-63
	adiw r28,82-63
	std Y+63,r13
	sbiw r28,82-63
	adiw r28,83-63
	std Y+63,r14
	sbiw r28,83-63
	adiw r28,84-63
	std Y+63,r15
	sbiw r28,84-63
	adiw r28,85-63
	std Y+63,r16
	sbiw r28,85-63
	adiw r28,86-63
	std Y+63,r17
	sbiw r28,86-63
	.loc 11 535 0
	mov r12,__zero_reg__
	mov r13,__zero_reg__
	mov r14,__zero_reg__
	mov r15,__zero_reg__
	ldi r16,0
	ldi r17,0
	call __cmpdi2
	brlo .L842
.L840:
	.loc 11 537 0
	ldi r20,lo8(5)
	ldi r21,0
.L975:
	.loc 11 542 0
	ldd r22,Y+33
	movw r24,r8
	call input_fault
.LVL1151:
	rjmp .L834
.L842:
	.loc 11 539 0
	ldd r11,Y+33
	cpse r11,__zero_reg__
	rjmp .L843
	adiw r28,67-60
	ldd r24,Y+60
	ldd r25,Y+61
	ldd r26,Y+62
	ldd r27,Y+63
	sbiw r28,67-60
	subi r24,96
	sbci r25,121
	sbci r26,-2
	sbci r27,-1
	cpi r24,-31
	sbci r25,-109
	sbci r26,4
	cpc r27,__zero_reg__
	brlo .+2
	rjmp .L844
	.loc 11 541 0
	ldd r10,Y+41
	ldd r11,Y+42
	ldd r12,Y+43
	ldd r13,Y+44
	cp r10,r4
	cpc r11,r5
	cpc r12,r6
	cpc r13,r7
	brne .+2
	rjmp .L878
	.loc 11 545 0
	ldi r24,lo8(4)
	movw r30,r28
	adiw r30,29
	movw r26,r2
	0:
	ld r0,Z+
	st X+,r0
	dec r24
	brne 0b
	movw r26,r2
	adiw r26,4
	ldi r24,lo8(8)
	movw r30,r28
	adiw r30,21
	0:
	ld r0,Z+
	st X+,r0
	dec r24
	brne 0b
	ldi r24,lo8(4)
	movw r30,r28
	adiw r30,17
	ldd r26,Y+55
	ldd r27,Y+56
	0:
	ld r0,Z+
	st X+,r0
	dec r24
	brne 0b
	.loc 11 546 0
	movw r26,r2
	adiw r26,16
	ldi r24,lo8(4)
	movw r30,r28
	adiw r30,13
	0:
	ld r0,Z+
	st X+,r0
	dec r24
	brne 0b
	ldi r24,lo8(1)
	movw r26,r2
	adiw r26,20
	st X,r24
	sbiw r26,20
	adiw r26,21
	st X,r24
	sbiw r26,21
	adiw r26,22
	st X,r24
	sbiw r26,22
	adiw r26,23
	st X,__zero_reg__
.LBE798:
.LBE797:
	.loc 11 547 0
	ldi r22,lo8(32)
	ldi r23,0
.L877:
.LBB805:
.LBB803:
	movw r24,r8
	call add_flags
.LVL1152:
	rjmp .L834
.L843:
	.loc 11 539 0
	ldd r17,Y+33
	cpi r17,lo8(1)
	brne .L846
	.loc 11 540 0
	adiw r28,67-60
	ldd r18,Y+60
	ldd r19,Y+61
	ldd r20,Y+62
	ldd r21,Y+63
	sbiw r28,67-60
	cpi r18,-95
	sbci r19,-122
	sbci r20,1
	cpc r21,__zero_reg__
	brlo .+2
	rjmp .L844
.L846:
	.loc 11 541 0
	ldd r10,Y+41
	ldd r11,Y+42
	ldd r12,Y+43
	ldd r13,Y+44
	cp r10,r4
	cpc r11,r5
	cpc r12,r6
	cpc r13,r7
	breq .L878
	.loc 11 545 0
	ldi r24,lo8(4)
	movw r30,r28
	adiw r30,29
	movw r26,r2
	0:
	ld r0,Z+
	st X+,r0
	dec r24
	brne 0b
	movw r26,r2
	adiw r26,4
	ldi r24,lo8(8)
	movw r30,r28
	adiw r30,21
	0:
	ld r0,Z+
	st X+,r0
	dec r24
	brne 0b
	ldi r24,lo8(4)
	movw r30,r28
	adiw r30,17
	ldd r26,Y+55
	ldd r27,Y+56
	0:
	ld r0,Z+
	st X+,r0
	dec r24
	brne 0b
	.loc 11 546 0
	movw r26,r2
	adiw r26,16
	ldi r24,lo8(4)
	movw r30,r28
	adiw r30,13
	0:
	ld r0,Z+
	st X+,r0
	dec r24
	brne 0b
	ldi r24,lo8(1)
	movw r26,r2
	adiw r26,20
	st X,r24
	sbiw r26,20
	adiw r26,21
	st X,r24
	sbiw r26,21
	adiw r26,22
	st X,r24
	sbiw r26,22
	adiw r26,23
	st X,__zero_reg__
.LBE803:
.LBE805:
	.loc 11 547 0
	ldi r22,lo8(64)
	ldi r23,0
	rjmp .L877
.L878:
.LVL1153:
.LBB806:
.LBB804:
.LBB801:
.LBB802:
	.loc 11 32 0
	movw r24,r2
	call r32
.LVL1154:
.LBE802:
.LBE801:
	.loc 11 542 0
	adiw r28,67-60
	ldd r10,Y+60
	ldd r11,Y+61
	ldd r12,Y+62
	ldd r13,Y+63
	sbiw r28,67-60
	cp r10,r22
	cpc r11,r23
	cpc r12,r24
	cpc r13,r25
	breq .+2
	rjmp .L847
	movw r24,r2
	adiw r24,4
	call r64
.LVL1155:
	movw r10,r18
	movw r12,r20
	movw r14,r22
	movw r16,r24
	ldd r18,Y+49
	ldd r19,Y+51
	ldd r20,Y+53
	ldd r21,Y+63
	adiw r28,75-63
	ldd r22,Y+63
	sbiw r28,75-63
	adiw r28,76-63
	ldd r23,Y+63
	sbiw r28,76-63
	adiw r28,77-63
	ldd r24,Y+63
	sbiw r28,77-63
	adiw r28,78-63
	ldd r25,Y+63
	sbiw r28,78-63
	call __cmpdi2
	breq .+2
	rjmp .L847
	movw r24,r2
	adiw r24,16
	call r32
.LVL1156:
	adiw r28,87-60
	ldd r12,Y+60
	ldd r13,Y+61
	ldd r14,Y+62
	ldd r15,Y+63
	sbiw r28,87-60
	cp r12,r22
	cpc r13,r23
	cpc r14,r24
	cpc r15,r25
	breq .+2
	rjmp .L847
.LVL1157:
.L834:
.LBE804:
.LBE806:
	.loc 11 740 0
	movw r30,r8
	subi r30,-100
	sbci r31,-1
	ld r24,Z
	ldd r25,Z+1
	eor r25,r24
	eor r24,r25
	eor r25,r24
	sbrc r25,0
	rjmp .L792
	sbiw r30,5
	ldd r24,Y+33
	subi r24,lo8(-(1))
	rjmp .L978
.LVL1158:
.L852:
.LBB807:
.LBB767:
.LBB757:
.LBB758:
	.loc 11 32 0
	movw r24,r4
	subi r24,-120
	sbci r25,-1
.LVL1159:
	call r32
.LVL1160:
	movw r12,r22
	movw r14,r24
.LVL1161:
.LBE758:
.LBE757:
.LBB759:
.LBB760:
	movw r24,r4
	subi r24,-68
	sbci r25,-1
.LVL1162:
	call r32
.LVL1163:
.LBE760:
.LBE759:
	.loc 11 659 0
	cp r12,r22
	cpc r13,r23
	cpc r14,r24
	cpc r15,r25
	brlt .+2
	rjmp .L891
.LVL1164:
.LBB761:
.LBB762:
	.loc 11 32 0
	movw r24,r4
	subi r24,-64
	sbci r25,-1
.LVL1165:
	call r32
.LVL1166:
.LBE762:
.LBE761:
	.loc 11 660 0
	cp r22,r12
	cpc r23,r13
	cpc r24,r14
	cpc r25,r15
	brge .+2
	rjmp .L849
.LVL1167:
.L853:
	.loc 11 661 0
	adiw r28,78-63
	ldd r18,Y+63
	sbiw r28,78-63
	cp r17,r18
	brne .+2
	rjmp .L849
	.loc 11 662 0
	movw r20,r8
	subi r20,-128
	sbci r21,-1
	std Y+34,r21
	std Y+33,r20
	movw r26,r20
	ld r6,X+
	ld r7,X
	movw r30,r6
	ldd r2,Z+12
	ldd r3,Z+13
	ldd r31,Z+14
	std Y+41,r31
	movw r26,r6
	adiw r26,15
	ld r27,X
	std Y+49,r27
	movw r30,r6
	ldd r31,Z+16
	std Y+51,r31
	movw r26,r6
	adiw r26,17
	ld r27,X
	std Y+53,r27
	movw r30,r6
	ldd r31,Z+18
	std Y+63,r31
	movw r26,r6
	adiw r26,19
	ld r27,X
	adiw r28,75-63
	std Y+63,r27
	sbiw r28,75-63
	movw r24,r4
	subi r24,-96
	sbci r25,-1
	call r64
.LVL1168:
	mov r27,r18
	mov r26,r19
	mov r31,r20
	mov r30,r21
	adiw r28,76-63
	std Y+63,r22
	sbiw r28,76-63
	adiw r28,77-63
	std Y+63,r23
	sbiw r28,77-63
	std Y+55,r24
	adiw r28,67-63
	std Y+63,r25
	sbiw r28,67-63
	movw r18,r2
	ldd r20,Y+41
	ldd r21,Y+49
	ldd r22,Y+51
	ldd r23,Y+53
	ldd r24,Y+63
	adiw r28,75-63
	ldd r25,Y+63
	sbiw r28,75-63
	mov r10,r27
.LVL1169:
	mov r11,r26
	mov r12,r31
	mov r13,r30
	adiw r28,76-63
	ldd r14,Y+63
	sbiw r28,76-63
	adiw r28,77-63
	ldd r15,Y+63
	sbiw r28,77-63
	ldd r16,Y+55
	adiw r28,67-63
	ldd r17,Y+63
	sbiw r28,67-63
	call __cmpdi2
	brsh .L854
	ldi r22,lo8(12)
	ldi r23,0
.L977:
.LBB763:
.LBB753:
	.loc 11 646 0
	movw r24,r8
	call unknown
.LVL1170:
	rjmp .L849
.LVL1171:
.L891:
.LBE753:
.LBE763:
.LBE767:
.LBE807:
	.loc 11 659 0
	ldi r16,lo8(1)
	adiw r28,78-63
	std Y+63,r16
	sbiw r28,78-63
.LVL1172:
	rjmp .L853
.LVL1173:
.L854:
.LBB808:
.LBB768:
	.loc 11 663 0
	movw r18,r2
	ldd r20,Y+41
	ldd r21,Y+49
	ldd r22,Y+51
	ldd r23,Y+53
	ldd r24,Y+63
	adiw r28,75-63
	ldd r25,Y+63
	sbiw r28,75-63
	adiw r28,76-63
	ldd r14,Y+63
	sbiw r28,76-63
	adiw r28,77-63
	ldd r15,Y+63
	sbiw r28,77-63
	ldd r16,Y+55
	adiw r28,67-63
	ldd r17,Y+63
	sbiw r28,67-63
	call __subdi3
.LVL1174:
	.loc 11 664 0
	movw r30,r4
	subi r30,-64
	sbci r31,-1
	adiw r28,78-63
	ldd r10,Y+63
	sbiw r28,78-63
.LBE768:
.LBE808:
	ldi r26,lo8(22)
	ldi r27,0
.LBB809:
.LBB769:
	tst r10
	breq .L855
.LBE769:
.LBE809:
	ldi r26,lo8(24)
	ldi r27,0
.L855:
.LBB810:
.LBB770:
	add r30,r26
	adc r31,r27
	ld r2,Z
	ldd r3,Z+1
	eor r3,r2
	eor r2,r3
	eor r3,r2
	movw r10,r2
	mov r13,__zero_reg__
	mov r12,__zero_reg__
	mov r14,__zero_reg__
	mov r15,__zero_reg__
	movw r16,r14
	std Y+41,r10
	std Y+42,r11
	std Y+43,r12
	std Y+44,r13
	std Y+45,r14
	std Y+46,r15
	std Y+47,r16
	std Y+48,r17
	mov r12,__zero_reg__
	mov r13,__zero_reg__
	mov r14,__zero_reg__
	mov r15,__zero_reg__
	ldi r16,0
	ldi r17,0
	call __cmpdi2
	brsh .+2
	rjmp .L849
.LVL1175:
.LBB764:
.LBB754:
	.loc 11 615 0
	movw r16,r8
	subi r16,-41
	sbci r17,-1
	adiw r28,91-62
	std Y+63,r17
	std Y+62,r16
	sbiw r28,91-62
	movw r24,r16
.LVL1176:
	call r32
.LVL1177:
	adiw r28,87-60
	std Y+60,r22
	std Y+61,r23
	std Y+62,r24
	std Y+63,r25
	sbiw r28,87-60
.LVL1178:
	.loc 11 616 0
	movw r30,r8
	subi r30,-103
	sbci r31,-1
	ld r24,Z
	ldi r18,lo8(1)
	ldi r20,lo8(4)
	ldi r22,lo8(4)
	ldi r23,0
.LVL1179:
	cpi r24,lo8(2)
	brlo .+2
	rjmp .L976
	.loc 11 617 0
	adiw r28,87-60
	ldd r18,Y+60
	ldd r19,Y+61
	ldd r20,Y+62
	ldd r21,Y+63
	sbiw r28,87-60
	cpi r18,-1
	sbci r19,-1
	sbci r20,-1
	sbci r21,-1
	breq .L857
	movw r24,r6
	subi r24,17
	sbci r25,-1
	call r32
.LVL1180:
	adiw r28,87-60
	ldd r10,Y+60
	ldd r11,Y+61
	ldd r12,Y+62
	ldd r13,Y+63
	sbiw r28,87-60
	cp r10,r22
	cpc r11,r23
	cpc r12,r24
	cpc r13,r25
	brlo .L858
.L857:
	.loc 11 618 0
	ldi r22,0
	ldi r23,lo8(4)
	movw r24,r8
	call add_flags
.LVL1181:
	ldi r18,lo8(1)
	ldi r20,lo8(5)
	ldi r22,lo8(14)
	ldi r23,0
	rjmp .L976
.LVL1182:
.L858:
	.loc 11 620 0
	ldi r22,lo8(1)
	movw r24,r8
	call guarded
.LVL1183:
	.loc 11 621 0
	cpse r24,__zero_reg__
	rjmp .L859
	movw r30,r8
	subi r30,-93
	sbci r31,-1
	ld r24,Z
.LVL1184:
	cpi r24,lo8(2)
	breq .+2
	rjmp .L894
	.loc 11 624 0
	ldd r26,Y+33
	ldd r27,Y+34
	ld r30,X+
	ld r31,X
	ldd r14,Z+12
	ldd r15,Z+13
	ldd r16,Z+14
	ldd r17,Z+15
	ldd r18,Z+16
	ldd r19,Z+17
	ldd r20,Z+18
	ldd r21,Z+19
	ldi r22,0
	movw r24,r8
	call account_ok
.LVL1185:
	ldi r18,lo8(1)
	ldi r20,lo8(5)
	ldi r22,lo8(15)
	ldi r23,0
	tst r24
	brne .+2
	rjmp .L976
	.loc 11 625 0
	ldd r26,Y+33
	ldd r27,Y+34
	ld r30,X+
	ld r31,X
	ldd r27,Z+12
	std Y+33,r27
	ldd r10,Z+13
.LVL1186:
	std Y+34,r10
	ldd r11,Z+14
	std Y+35,r11
	ldd r12,Z+15
	std Y+36,r12
	ldd r13,Z+16
	std Y+37,r13
	ldd r14,Z+17
	std Y+38,r14
	ldd r15,Z+18
	std Y+39,r15
	ldd r16,Z+19
	std Y+40,r16
.LVL1187:
.LBB743:
.LBB744:
	.loc 11 593 0
	movw r24,r8
	adiw r24,33
	call r64
.LVL1188:
	movw r6,r18
	movw r4,r20
	mov r27,r22
	mov r26,r23
	mov r3,r24
	mov r2,r25
.LVL1189:
	.loc 11 594 0
	movw r24,r8
	subi r24,124
	sbci r25,-1
	movw r30,r24
	ld __tmp_reg__,Z+
	ld r31,Z
	mov r30,__tmp_reg__
	std Y+56,r31
	std Y+55,r30
	.loc 11 595 0
	movw r24,r30
	subi r24,-90
	sbci r25,-1
	movw r30,r24
	ld r24,Z
	ldd r25,Z+1
	eor r25,r24
	eor r24,r25
	eor r25,r24
	movw r10,r24
	mov r13,__zero_reg__
	mov r12,__zero_reg__
	mov r14,__zero_reg__
	mov r15,__zero_reg__
	movw r16,r14
	adiw r28,79-63
	std Y+63,r10
	sbiw r28,79-63
	adiw r28,80-63
	std Y+63,r11
	sbiw r28,80-63
	adiw r28,81-63
	std Y+63,r12
	sbiw r28,81-63
	adiw r28,82-63
	std Y+63,r13
	sbiw r28,82-63
	adiw r28,83-63
	std Y+63,r14
	sbiw r28,83-63
	adiw r28,84-63
	std Y+63,r15
	sbiw r28,84-63
	adiw r28,85-63
	std Y+63,r16
	sbiw r28,85-63
	adiw r28,86-63
	std Y+63,r17
	sbiw r28,86-63
	movw r18,r6
	movw r20,r4
	mov r22,r27
	mov r23,r26
	mov r24,r3
	mov r25,r2
	mov r12,__zero_reg__
	mov r13,__zero_reg__
	mov r14,__zero_reg__
	mov r15,__zero_reg__
	ldi r16,0
	ldi r17,0
	call __cmpdi2
	breq .+2
	brsh .+2
	rjmp .L863
	.loc 11 597 0
	ldi r18,lo8(1)
	ldi r19,0
	ldi r20,0
	ldi r21,0
	ldi r22,0
.LVL1190:
	ldi r23,0
.LVL1191:
	ldi r24,0
	ldi r25,0
	call __subdi3
	movw r10,r6
	movw r12,r4
	mov r14,r27
	mov r15,r26
	mov r16,r3
	mov r17,r2
	call __adddi3
	std Y+41,r18
	std Y+49,r19
	std Y+51,r20
	std Y+53,r21
	std Y+63,r22
	adiw r28,75-63
	std Y+63,r23
	sbiw r28,75-63
	adiw r28,76-63
	std Y+63,r24
	sbiw r28,76-63
	adiw r28,77-63
	std Y+63,r25
	sbiw r28,77-63
.LVL1192:
.LBB745:
	.loc 11 600 0
	ldd r24,Y+55
	ldd r25,Y+56
	subi r24,-124
	sbci r25,-1
	call r64
.LVL1193:
	mov r27,r18
	mov r26,r19
	adiw r28,93-63
	std Y+63,r20
	sbiw r28,93-63
	adiw r28,94-63
	std Y+63,r21
	sbiw r28,94-63
	movw r4,r22
	movw r6,r24
.LVL1194:
	.loc 11 601 0
	ldd r24,Y+55
	ldd r25,Y+56
	subi r24,-82
	sbci r25,-1
	movw r30,r24
	ld r2,Z
	ldd r3,Z+1
	eor r3,r2
	eor r2,r3
	eor r3,r2
	movw r10,r2
	mov r13,__zero_reg__
	mov r12,__zero_reg__
	mov r14,__zero_reg__
	mov r15,__zero_reg__
	movw r16,r14
	adiw r28,67-63
	std Y+63,r10
	sbiw r28,67-63
	adiw r28,68-63
	std Y+63,r11
	sbiw r28,68-63
	adiw r28,69-63
	std Y+63,r12
	sbiw r28,69-63
	adiw r28,70-63
	std Y+63,r13
	sbiw r28,70-63
	adiw r28,71-63
	std Y+63,r14
	sbiw r28,71-63
	adiw r28,72-63
	std Y+63,r15
	sbiw r28,72-63
	adiw r28,73-63
	std Y+63,r16
	sbiw r28,73-63
	adiw r28,74-63
	std Y+63,r17
	sbiw r28,74-63
	com r10
	com r11
	mov r18,r27
	mov r19,r26
	movw r22,r4
	movw r24,r6
	clr r12
	dec r12
	clr r13
	dec r13
	clr r14
	dec r14
	clr r15
	dec r15
	ldi r16,lo8(-1)
	ldi r17,lo8(-1)
	call __cmpdi2
	brsh .L864
.LVL1195:
	adiw r28,67-63
	ldd r10,Y+63
	sbiw r28,67-63
	adiw r28,68-63
	ldd r11,Y+63
	sbiw r28,68-63
	mov r12,__zero_reg__
	mov r13,__zero_reg__
	mov r14,__zero_reg__
	mov r15,__zero_reg__
	ldi r16,0
	ldi r17,0
	call __adddi3
.LVL1196:
	movw r6,r18
.LVL1197:
	movw r4,r20
	mov r27,r22
	mov r26,r23
	mov r31,r24
	mov r30,r25
	ldd r18,Y+41
	ldd r19,Y+49
	ldd r20,Y+51
	ldd r21,Y+53
	ldd r22,Y+63
	adiw r28,75-63
	ldd r23,Y+63
	sbiw r28,75-63
	adiw r28,76-63
	ldd r24,Y+63
	sbiw r28,76-63
	adiw r28,77-63
	ldd r25,Y+63
	sbiw r28,77-63
	movw r10,r6
	movw r12,r4
	mov r14,r27
	mov r15,r26
	mov r16,r31
	mov r17,r30
	call __cmpdi2
	breq .L864
	brlo .L864
.LVL1198:
	std Y+41,r6
.LVL1199:
	std Y+49,r7
	std Y+51,r4
	std Y+53,r5
	std Y+63,r27
	adiw r28,75-63
	std Y+63,r26
	sbiw r28,75-63
	adiw r28,76-63
	std Y+63,r31
	sbiw r28,76-63
	adiw r28,77-63
	std Y+63,r30
	sbiw r28,77-63
.LVL1200:
.L864:
	.loc 11 600 0
	ldd r24,Y+55
	ldd r25,Y+56
	subi r24,108
	sbci r25,-1
	call r64
.LVL1201:
	mov r27,r18
	mov r26,r19
	adiw r28,93-63
	std Y+63,r20
	sbiw r28,93-63
	adiw r28,94-63
	std Y+63,r21
	sbiw r28,94-63
	movw r4,r22
	movw r6,r24
.LVL1202:
	.loc 11 601 0
	ldd r24,Y+55
	ldd r25,Y+56
	subi r24,-84
	sbci r25,-1
	movw r30,r24
	ld r2,Z
	ldd r3,Z+1
	eor r3,r2
	eor r2,r3
	eor r3,r2
	movw r10,r2
	mov r13,__zero_reg__
	mov r12,__zero_reg__
	mov r14,__zero_reg__
	mov r15,__zero_reg__
	movw r16,r14
	adiw r28,67-63
	std Y+63,r10
	sbiw r28,67-63
	adiw r28,68-63
	std Y+63,r11
	sbiw r28,68-63
	adiw r28,69-63
	std Y+63,r12
	sbiw r28,69-63
	adiw r28,70-63
	std Y+63,r13
	sbiw r28,70-63
	adiw r28,71-63
	std Y+63,r14
	sbiw r28,71-63
	adiw r28,72-63
	std Y+63,r15
	sbiw r28,72-63
	adiw r28,73-63
	std Y+63,r16
	sbiw r28,73-63
	adiw r28,74-63
	std Y+63,r17
	sbiw r28,74-63
	com r10
	com r11
	mov r18,r27
	mov r19,r26
	movw r22,r4
	movw r24,r6
	clr r12
	dec r12
	clr r13
	dec r13
	clr r14
	dec r14
	clr r15
	dec r15
	ldi r16,lo8(-1)
	ldi r17,lo8(-1)
	call __cmpdi2
	brsh .L866
	adiw r28,67-63
	ldd r10,Y+63
	sbiw r28,67-63
	adiw r28,68-63
	ldd r11,Y+63
	sbiw r28,68-63
	mov r12,__zero_reg__
	mov r13,__zero_reg__
	mov r14,__zero_reg__
	mov r15,__zero_reg__
	ldi r16,0
	ldi r17,0
	call __adddi3
.LVL1203:
	movw r6,r18
.LVL1204:
	movw r4,r20
	mov r27,r22
	mov r26,r23
	mov r31,r24
	mov r30,r25
	ldd r18,Y+41
	ldd r19,Y+49
	ldd r20,Y+51
	ldd r21,Y+53
	ldd r22,Y+63
	adiw r28,75-63
	ldd r23,Y+63
	sbiw r28,75-63
	adiw r28,76-63
	ldd r24,Y+63
	sbiw r28,76-63
	adiw r28,77-63
	ldd r25,Y+63
	sbiw r28,77-63
	movw r10,r6
	movw r12,r4
	mov r14,r27
	mov r15,r26
	mov r16,r31
	mov r17,r30
	call __cmpdi2
	breq .L866
	brlo .L866
	std Y+41,r6
.LVL1205:
	std Y+49,r7
.LVL1206:
	std Y+51,r4
.LVL1207:
	std Y+53,r5
.LVL1208:
	std Y+63,r27
.LVL1209:
	adiw r28,75-63
	std Y+63,r26
	sbiw r28,75-63
.LVL1210:
	adiw r28,76-63
	std Y+63,r31
	sbiw r28,76-63
.LVL1211:
	adiw r28,77-63
	std Y+63,r30
	sbiw r28,77-63
.LVL1212:
.L866:
.LBE745:
	.loc 11 604 0
	ldd r30,Y+55
	ldd r31,Y+56
	subi r30,-116
	sbci r31,-1
	ld r24,Z
	tst r24
	brne .+2
	rjmp .L868
.LBB746:
	.loc 11 605 0
	movw r24,r8
	subi r24,-89
	sbci r25,-1
	call r32
.LVL1213:
	.loc 11 606 0
	movw r30,r8
	subi r30,126
	sbci r31,-1
	ld __tmp_reg__,Z+
	ld r31,Z
	mov r30,__tmp_reg__
	ldd r16,Z+8
	ldd r17,Z+9
	ldd r18,Z+10
	ldd r19,Z+11
	cp r22,r16
	cpc r23,r17
	cpc r24,r18
	cpc r25,r19
	brlo .+2
	rjmp .L863
	.loc 11 607 0
	movw r2,r16
	movw r4,r18
	sub r2,r22
	sbc r3,r23
	sbc r4,r24
	sbc r5,r25
.LVL1214:
	ldd r24,Y+55
	ldd r25,Y+56
	subi r24,-96
	sbci r25,-1
	call r64
.LVL1215:
	mov r27,r18
	mov r26,r19
	adiw r28,93-63
	std Y+63,r22
	sbiw r28,93-63
	adiw r28,94-63
	std Y+63,r23
	sbiw r28,94-63
	.loc 11 608 0
	movw r14,r4
	movw r12,r2
	ldi r16,0
	ldi r17,0
	movw r18,r16
	adiw r28,67-63
	std Y+63,r2
	sbiw r28,67-63
	adiw r28,68-63
	std Y+63,r13
	sbiw r28,68-63
	adiw r28,69-63
	std Y+63,r4
	sbiw r28,69-63
	adiw r28,70-63
	std Y+63,r15
	sbiw r28,70-63
	adiw r28,71-63
	std Y+63,r16
	sbiw r28,71-63
	adiw r28,72-63
	std Y+63,r17
	sbiw r28,72-63
	adiw r28,73-63
	std Y+63,r18
	sbiw r28,73-63
	adiw r28,74-63
	std Y+63,r19
	sbiw r28,74-63
	mov r10,r2
	com r10
	mov r11,r13
	com r11
	mov r12,r4
	com r12
	mov r13,r15
	com r13
	mov r18,r27
	mov r19,r26
	clr r14
	dec r14
	clr r15
	dec r15
	ldi r16,lo8(-1)
	ldi r17,lo8(-1)
	call __cmpdi2
	brsh .L868
	adiw r28,67-63
	ldd r10,Y+63
	sbiw r28,67-63
	adiw r28,68-63
	ldd r11,Y+63
	sbiw r28,68-63
	adiw r28,69-63
	ldd r12,Y+63
	sbiw r28,69-63
	adiw r28,70-63
	ldd r13,Y+63
	sbiw r28,70-63
	mov r14,__zero_reg__
	mov r15,__zero_reg__
	ldi r16,0
	ldi r17,0
	call __adddi3
	movw r6,r18
	movw r4,r20
	mov r27,r22
	mov r26,r23
	mov r31,r24
	mov r30,r25
	ldd r18,Y+41
	ldd r19,Y+49
	ldd r20,Y+51
	ldd r21,Y+53
	ldd r22,Y+63
	adiw r28,75-63
	ldd r23,Y+63
	sbiw r28,75-63
	adiw r28,76-63
	ldd r24,Y+63
	sbiw r28,76-63
	adiw r28,77-63
	ldd r25,Y+63
	sbiw r28,77-63
	movw r10,r6
	movw r12,r4
	mov r14,r27
	mov r15,r26
	mov r16,r31
	mov r17,r30
	call __cmpdi2
	breq .L868
	brlo .L868
	std Y+41,r6
.LVL1216:
	std Y+49,r7
.LVL1217:
	std Y+51,r4
.LVL1218:
	std Y+53,r5
.LVL1219:
	std Y+63,r27
.LVL1220:
	adiw r28,75-63
	std Y+63,r26
	sbiw r28,75-63
.LVL1221:
	adiw r28,76-63
	std Y+63,r31
	sbiw r28,76-63
.LVL1222:
	adiw r28,77-63
	std Y+63,r30
	sbiw r28,77-63
.LVL1223:
.L868:
.LBE746:
.LBE744:
.LBE743:
	.loc 11 627 0
	ldd r18,Y+33
	ldd r19,Y+34
	ldd r20,Y+35
	ldd r21,Y+36
	ldd r22,Y+37
	ldd r23,Y+38
	ldd r24,Y+39
	ldd r25,Y+40
	ldd r10,Y+41
	ldd r11,Y+49
	ldd r12,Y+51
	ldd r13,Y+53
	ldd r14,Y+63
	adiw r28,75-63
	ldd r15,Y+63
	sbiw r28,75-63
	adiw r28,76-63
	ldd r16,Y+63
	sbiw r28,76-63
	adiw r28,77-63
	ldd r17,Y+63
	sbiw r28,77-63
	call __cmpdi2
	brlo .L870
.L863:
	ldi r18,lo8(1)
	ldi r20,lo8(5)
	ldi r22,lo8(16)
	ldi r23,0
	jmp .L976
.LVL1224:
.L859:
.LBE754:
.LBE764:
.LBE770:
.LBE810:
	.loc 11 622 0
	ldi r22,lo8(7)
	ldi r23,0
.LBB811:
.LBB771:
.LBB765:
.LBB755:
	cpi r24,lo8(26)
	breq .L860
.LVL1225:
.L894:
.LBE755:
.LBE765:
.LBE771:
.LBE811:
	ldi r22,lo8(10)
	ldi r23,0
.L860:
.LBB812:
.LBB772:
.LBB766:
.LBB756:
	ldi r18,lo8(1)
	ldi r20,lo8(5)
	jmp .L976
.LVL1226:
.L870:
	.loc 11 628 0
	adiw r28,79-63
	ldd r10,Y+63
	sbiw r28,79-63
	com r10
	adiw r28,80-63
	ldd r11,Y+63
	sbiw r28,80-63
	com r11
	ldd r18,Y+33
	ldd r19,Y+34
	ldd r20,Y+35
	ldd r21,Y+36
	ldd r22,Y+37
	ldd r23,Y+38
	ldd r24,Y+39
	ldd r25,Y+40
	clr r12
	dec r12
	clr r13
	dec r13
	clr r14
	dec r14
	clr r15
	dec r15
	ldi r16,lo8(-1)
	ldi r17,lo8(-1)
	call __cmpdi2
	brlo .L871
	ldi r22,lo8(14)
	ldi r23,0
	rjmp .L977
.L871:
	.loc 11 629 0
	movw r6,r8
	ldi r16,103
	add r6,r16
	adc r7,__zero_reg__
	movw r30,r8
	subi r30,-102
	sbci r31,-1
	ld r3,Z
	movw r26,r6
	ld r24,X
	add r24,r3
	andi r24,lo8(1)
	mov r11,r24
.LVL1227:
	ldi r18,lo8(44)
	ldd r24,Y+55
	ldd r25,Y+56
	mul r11,r18
	add r24,r0
	adc r25,r1
	clr __zero_reg__
	movw r30,r24
	subi r30,88
	sbci r31,-1
	movw r4,r30
.LVL1228:
	.loc 11 630 0
	movw r26,r30
	0:
	st X+,__zero_reg__
	dec r18
	brne 0b
	adiw r28,87-60
	ldd r12,Y+60
	ldd r13,Y+61
	ldd r14,Y+62
	ldd r15,Y+63
	sbiw r28,87-60
	ldi r27,-1
	sub r12,r27
	sbc r13,r27
	sbc r14,r27
	sbc r15,r27
	movw r22,r14
	movw r20,r12
	movw r24,r30
	call w32
.LVL1229:
	movw r30,r4
	adiw r30,4
	adiw r28,67-62
	std Y+63,r31
	std Y+62,r30
	sbiw r28,67-62
	ldd r16,Y+33
	ldd r17,Y+34
	ldd r18,Y+35
	ldd r19,Y+36
	ldd r20,Y+37
	ldd r21,Y+38
	ldd r22,Y+39
	ldd r23,Y+40
	movw r24,r30
	call w64
.LVL1230:
	.loc 11 631 0
	movw r26,r4
	adiw r26,12
	movw r2,r8
	ldi r31,-124
	add r2,r31
	adc r3,__zero_reg__
	movw r30,r2
	ld r24,Z
	ldd r25,Z+1
	movw r30,r24
	subi r30,124
	sbci r31,-1
	ldi r24,lo8(4)
	0:
	ld r0,Z+
	st X+,r0
	dec r24
	brne 0b
	movw r26,r4
	adiw r26,16
	movw r30,r2
	ld r24,Z
	ldd r25,Z+1
	movw r30,r24
	subi r30,-120
	sbci r31,-1
	ldi r24,lo8(4)
	0:
	ld r0,Z+
	st X+,r0
	dec r24
	brne 0b
	.loc 11 632 0
	movw r26,r2
	ld r24,X+
	ld r25,X
	subi r24,-124
	sbci r25,-1
	call r64
.LVL1231:
	std Y+55,r18
	std Y+56,r19
	std Y+57,r20
	std Y+58,r21
	std Y+59,r22
	std Y+60,r23
	std Y+61,r24
	std Y+62,r25
	ldd r24,Y+33
	ldd r25,Y+34
	ldd r30,Y+55
	ldd r31,Y+56
	sub r24,r30
	sbc r25,r31
.LVL1232:
.LBB747:
.LBB748:
	.loc 11 35 0
	movw r26,r4
	adiw r26,20
	st X,r25
	sbiw r26,20
	adiw r26,21
	st X,r24
	sbiw r26,21
.LVL1233:
.LBE748:
.LBE747:
	.loc 11 633 0
	adiw r26,22
	movw r30,r2
	ld r24,Z
	ldd r25,Z+1
	movw r30,r24
	subi r30,100
	sbci r31,-1
	ldi r24,lo8(4)
	0:
	ld r0,Z+
	st X+,r0
	dec r24
	brne 0b
	ldi r16,lo8(-1)
	ldi r17,lo8(-1)
	ldi r18,lo8(-1)
	ldi r19,lo8(-1)
	ldi r20,lo8(-1)
	ldi r21,lo8(-1)
	ldi r22,lo8(-1)
	ldi r23,lo8(-1)
	movw r24,r4
	adiw r24,26
	call w64
.LVL1234:
	.loc 11 634 0
	movw r26,r2
	ld r30,X+
	ld r31,X
	subi r30,-116
	sbci r31,-1
	ld r24,Z
	movw r30,r4
	std Z+38,r24
	adiw r28,78-63
	ldd r10,Y+63
	sbiw r28,78-63
	std Z+39,r10
	ldi r24,lo8(9)
	std Z+40,r24
	.loc 11 635 0
	movw r22,r14
	movw r20,r12
	adiw r28,91-62
	ldd r24,Y+62
	ldd r25,Y+63
	sbiw r28,91-62
	call w32
.LVL1235:
	movw r26,r6
	ld r24,X
	subi r24,lo8(-(1))
	st X,r24
	movw r30,r8
	subi r30,-104
	sbci r31,-1
	st Z,r11
	ldi r22,lo8(1)
	ldi r23,0
	movw r24,r8
	call add_flags
.LVL1236:
	.loc 11 637 0
	movw r30,r28
	adiw r30,1
	movw r10,r30
	ldd r12,Y+41
	ldd r13,Y+49
	ldd r14,Y+51
	ldd r15,Y+53
	ldd r16,Y+63
	adiw r28,75-63
	ldd r17,Y+63
	sbiw r28,75-63
	adiw r28,76-63
	ldd r18,Y+63
	sbiw r28,76-63
	adiw r28,77-63
	ldd r19,Y+63
	sbiw r28,77-63
	adiw r28,78-63
	ldd r20,Y+63
	sbiw r28,78-63
	ldi r22,lo8(2)
	movw r24,r8
	call driver
.LVL1237:
	.loc 11 638 0
	movw r30,r8
	subi r30,-93
	sbci r31,-1
	ld r24,Z
	cpi r24,lo8(2)
	breq .+2
	rjmp .L872
	adiw r30,35
	ld r26,Z
	ldd r27,Z+1
	movw r30,r26
	subi r30,-74
	sbci r31,-1
	ld r18,Z
	sbrs r18,4
	rjmp .L872
	.loc 11 639 0
	adiw r26,12
	ld r30,X
	sbiw r26,12
	adiw r26,13
	ld r31,X
	sbiw r26,13
	adiw r26,14
	ld r10,X
	sbiw r26,14
	std Y+55,r10
	adiw r26,15
	ld r11,X
	sbiw r26,15
.LVL1238:
	adiw r28,79-63
	std Y+63,r11
	sbiw r28,79-63
	adiw r26,16
	ld r12,X
	sbiw r26,16
	adiw r28,87-63
	std Y+63,r12
	sbiw r28,87-63
.LVL1239:
	adiw r26,17
	ld r13,X
	sbiw r26,17
	adiw r28,91-63
	std Y+63,r13
	sbiw r28,91-63
	adiw r26,18
	ld r7,X
	sbiw r26,18
	adiw r26,19
	ld r6,X
	.loc 11 638 0
	movw r18,r30
	movw r20,r10
	movw r22,r12
	mov r24,r7
	mov r25,r6
	ldd r10,Y+41
	ldd r11,Y+49
	ldd r12,Y+51
	ldd r13,Y+53
	ldd r14,Y+63
	adiw r28,75-63
	ldd r15,Y+63
	sbiw r28,75-63
	adiw r28,76-63
	ldd r16,Y+63
	sbiw r28,76-63
	adiw r28,77-63
	ldd r17,Y+63
	sbiw r28,77-63
	call __cmpdi2
	brsh .L872
	.loc 11 639 0
	push r17
	adiw r28,76-63
	ldd r14,Y+63
	sbiw r28,76-63
	push r14
	adiw r28,75-63
	ldd r15,Y+63
	sbiw r28,75-63
	push r15
	ldd r16,Y+63
	push r16
	ldd r17,Y+53
	push r17
	ldd r18,Y+51
	push r18
	ldd r19,Y+49
	push r19
	ldd r20,Y+41
	push r20
	push r6
	push r7
	adiw r28,91-63
	ldd r26,Y+63
	sbiw r28,91-63
	push r26
	adiw r28,87-63
	ldd r27,Y+63
	sbiw r28,87-63
	push r27
	adiw r28,79-63
	ldd r26,Y+63
	sbiw r28,79-63
	push r26
	ldd r27,Y+55
	push r27
	push r31
	push r30
	ldd r14,Y+33
	ldd r15,Y+34
	ldd r16,Y+35
	ldd r17,Y+36
	ldd r18,Y+37
	ldd r19,Y+38
	ldd r20,Y+39
	ldd r21,Y+40
	adiw r28,78-63
	ldd r22,Y+63
	sbiw r28,78-63
	movw r24,r28
	adiw r24,1
	call dispatch_report
.LVL1240:
	in __tmp_reg__,__SREG__
	cli
	out __SP_H__,r29
	out __SREG__,__tmp_reg__
	out __SP_L__,r28
	cpse r24,__zero_reg__
	rjmp .L873
.L872:
	.loc 11 640 0
	movw r26,r4
	adiw r26,40
	ld r24,X
	sbiw r26,40
	andi r24,lo8(-8)
	ori r24,lo8(5)
	adiw r26,40
	st X,r24
	sbiw r26,40
.LVL1241:
.LBB749:
.LBB750:
	.loc 11 35 0
	adiw r26,42
	st X,__zero_reg__
	sbiw r26,42
	ldi r24,lo8(13)
	adiw r26,43
	st X,r24
.LVL1242:
.LBE750:
.LBE749:
	.loc 11 640 0
	ldi r22,lo8(13)
	ldi r23,0
	rjmp .L977
.L873:
	.loc 11 642 0
	movw r24,r28
	adiw r24,21
	call r64
.LVL1243:
	movw r14,r18
	movw r16,r20
	movw r18,r22
	movw r20,r24
	ldi r22,lo8(1)
	movw r24,r8
	call account_ok
.LVL1244:
	ldi r22,lo8(15)
	ldi r23,0
	tst r24
	brne .+2
	rjmp .L977
	.loc 11 645 0
	movw r24,r28
	adiw r24,21
	call r64
.LVL1245:
	std Y+41,r18
	std Y+49,r19
	std Y+51,r20
	mov r6,r21
	mov r7,r22
	std Y+53,r23
	std Y+63,r24
	adiw r28,75-63
	std Y+63,r25
	sbiw r28,75-63
	movw r30,r2
	ld __tmp_reg__,Z+
	ld r31,Z
	mov r30,__tmp_reg__
	std Y+34,r31
	std Y+33,r30
.LVL1246:
	movw r24,r30
	subi r24,-124
	sbci r25,-1
	call r64
.LVL1247:
	movw r10,r18
	movw r12,r20
	movw r14,r22
	movw r16,r24
	ldd r18,Y+41
	ldd r19,Y+49
	ldd r20,Y+51
	mov r21,r6
	mov r22,r7
	ldd r23,Y+53
	ldd r24,Y+63
	adiw r28,75-63
	ldd r25,Y+63
	sbiw r28,75-63
	call __subdi3
	ldd r30,Y+33
	ldd r31,Y+34
	subi r30,-82
	sbci r31,-1
	ld __tmp_reg__,Z+
	ld r31,Z
	mov r30,__tmp_reg__
	eor r31,r30
	eor r30,r31
	eor r31,r30
	movw r10,r30
	mov r13,__zero_reg__
	mov r12,__zero_reg__
	mov r14,__zero_reg__
	mov r15,__zero_reg__
	movw r16,r14
	std Y+33,r10
	std Y+34,r11
	std Y+35,r12
	std Y+36,r13
	std Y+37,r14
	std Y+38,r15
	std Y+39,r16
	std Y+40,r17
	mov r12,__zero_reg__
	mov r13,__zero_reg__
	mov r14,__zero_reg__
	mov r15,__zero_reg__
	ldi r16,0
	ldi r17,0
	call __cmpdi2
	brlo .L875
	.loc 11 646 0
	ldi r22,lo8(16)
	ldi r23,0
	rjmp .L977
.L875:
	.loc 11 648 0
	ldd r16,Y+41
	ldd r17,Y+49
	ldd r18,Y+51
	mov r19,r6
	mov r20,r7
	ldd r21,Y+53
	ldd r22,Y+63
	adiw r28,75-63
	ldd r23,Y+63
	sbiw r28,75-63
	adiw r28,67-62
	ldd r24,Y+62
	ldd r25,Y+63
	sbiw r28,67-62
	call w64
.LVL1248:
	movw r24,r28
	adiw r24,21
	call r64
.LVL1249:
	std Y+33,r18
	std Y+34,r19
	std Y+35,r20
	std Y+36,r21
	std Y+37,r22
	std Y+38,r23
	std Y+39,r24
	std Y+40,r25
	movw r26,r2
	ld r24,X+
	ld r25,X
	subi r24,-124
	sbci r25,-1
	call r64
.LVL1250:
	movw r10,r18
	ldd r24,Y+33
	ldd r25,Y+34
	sub r24,r10
	sbc r25,r11
.LVL1251:
.LBB751:
.LBB752:
	.loc 11 35 0
	movw r30,r4
	std Z+20,r25
	std Z+21,r24
.LVL1252:
.LBE752:
.LBE751:
	.loc 11 649 0
	movw r24,r28
	adiw r24,21
	call r64
.LVL1253:
	movw r26,r2
	ld r30,X+
	ld r31,X
	movw r16,r18
	movw r18,r20
	movw r20,r22
	movw r22,r24
	movw r24,r30
	subi r24,-96
	sbci r25,-1
	call w64
.LVL1254:
	movw r26,r2
	ld r30,X+
	ld r31,X
	movw r26,r30
	subi r26,-116
	sbci r27,-1
	adiw r28,78-63
	ldd r10,Y+63
	sbiw r28,78-63
	st X,r10
	.loc 11 650 0
	sbiw r26,4
	subi r30,-120
	sbci r31,-1
	ldi r24,lo8(4)
	0:
	ld r0,Z+
	st X+,r0
	dec r24
	brne 0b
	.loc 11 651 0
	movw r24,r28
	adiw r24,21
	call r64
.LVL1255:
	movw r10,r18
	movw r12,r20
	movw r14,r22
	movw r16,r24
	movw r26,r2
	ld r30,X+
	ld r31,X
	movw r26,r30
	subi r26,-90
	sbci r27,-1
	ld r20,X+
	ld r21,X
	eor r21,r20
	eor r20,r21
	eor r21,r20
	movw r18,r20
	ldi r20,0
	ldi r21,0
	ldi r22,0
	ldi r23,0
	ldi r24,0
	ldi r25,0
	call __adddi3
	movw r16,r18
	movw r18,r20
	movw r20,r22
	movw r22,r24
	movw r24,r30
	subi r24,-104
	sbci r25,-1
	call w64
.LVL1256:
	jmp .L849
.LBE756:
.LBE766:
.LBE772:
.LBE812:
	.cfi_endproc
.LFE153:
	.size	hms_standing_poll, .-hms_standing_poll
