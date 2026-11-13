/* Print the firmware's constant tables as JSON so tests/test_tables.py can compare them with
 * cad/params.py and with arm.sidecar.json (limits, ratios, torque caps, tool IDs, the BHMS
 * action/property layouts). Host-only helper. */
#include <stdio.h>
#include <string.h>

#include "arm_device.h"

static int rd(void *c) { (void)c; return -1; }
static void wr(void *c, const uint8_t *b, size_t n) { (void)c; (void)b; (void)n; }
static uint32_t ms(void *c) { (void)c; return 0; }

static const char *type_name(uint8_t t) {
    static const char *const n[] = {"?", "u8", "i8", "u16", "i16", "u32", "i32", "f32", "bool"};
    return t < 9 ? n[t] : "?";
}

static void fields(const bhms_field *f, uint8_t n) {
    uint8_t i;
    printf("[");
    for (i = 0; i < n; ++i) {
        printf("%s{\"type\":\"%s\"", i ? "," : "", type_name(f[i].type));
        if (f[i].has_range) {
            if (f[i].type == BHMS_F32) printf(",\"lo\":%g,\"hi\":%g", (double)f[i].flo, (double)f[i].fhi);
            else printf(",\"lo\":%d,\"hi\":%d", (int)f[i].ilo, (int)f[i].ihi);
        }
        printf("}");
    }
    printf("]");
}

int main(void) {
    unsigned i, j;
    arm a;
    arm_device d;
    bhms_hal hal = {0, rd, wr, ms, 0, 0, 0};
    arm_hw hw = {0};
    const bhms_device *dev;
    (void)hw;
    printf("{\"servos\":[");
    for (i = 0; i < ARM_NUM_SERVOS; ++i)
        printf("%s{\"name\":\"%s\",\"id\":%u,\"lo\":%g,\"hi\":%g,\"ratio\":%g,\"torque\":%u}", i ? "," : "",
               kArmServos[i].name, kArmServos[i].servo_id, (double)kArmServos[i].lo_deg,
               (double)kArmServos[i].hi_deg, (double)kArmServos[i].ratio, kArmServos[i].torque_permille);
    printf("],\"coupled\":[");
    for (i = 0; i < ARM_NUM_COUPLED; ++i) {
        printf("%s{\"name\":\"%s\",\"joints\":[", i ? "," : "", kArmCoupled[i].name);
        for (j = 0; j < kArmCoupled[i].n_joints; ++j)
            printf("%s\"%s\"", j ? "," : "", kArmServos[kArmCoupled[i].joints[j]].name);
        printf("],\"lo\":%g,\"hi\":%g}", (double)kArmCoupled[i].lo_deg, (double)kArmCoupled[i].hi_deg);
    }
    printf("],\"rest\":[%g,%g,%g,%g,%g],\"noload\":%g,\"margin\":%g,\"pullup\":%g,\"tools\":[",
           (double)kArmRestPose[0], (double)kArmRestPose[1], (double)kArmRestPose[2],
           (double)kArmRestPose[3], (double)kArmRestPose[4], (double)ARM_SERVO_NOLOAD_RAD_S,
           (double)ARM_ENABLE_MARGIN_DEG, (double)ARM_TOOL_PULLUP_OHM);
    for (i = 0; i < 8; ++i)
        printf("%s{\"code\":%u,\"name\":\"%s\",\"r\":%g}", i ? "," : "", kArmTools[i].code, kArmTools[i].name,
               (double)kArmTools[i].r_id_ohm);
    printf("],");
    /* Device tables. */
    memset(&a, 0, sizeof a);
    if (arm_device_init(&d, &a, &hal) != BHMS_OK) return 1;
    dev = arm_device_table(&d);
    printf("\"digest8\":[");
    for (i = 0; i < 8; ++i) printf("%s%u", i ? "," : "", dev->digest8[i]);
    printf("],\"fencing\":%u,\"stop\":%u,\"actions\":[", dev->flags & BHMS_DEV_FENCING ? 1u : 0u,
           dev->stop != 0 ? 1u : 0u);
    for (i = 0; i < dev->n_actions; ++i) {
        const bhms_action *x = &dev->actions[i];
        printf("%s{\"index\":%u,\"lease\":%u,\"cancel\":%u,\"args\":", i ? "," : "", i,
               x->flags & BHMS_ACT_REQUIRES_LEASE ? 1u : 0u, x->cancel != 0 ? 1u : 0u);
        fields(x->args, x->n_args);
        printf(",\"results\":");
        fields(x->results, x->n_results);
        printf("}");
    }
    printf("],\"properties\":[");
    for (i = 0; i < dev->n_properties; ++i)
        printf("%s{\"index\":%u,\"type\":\"%s\"}", i ? "," : "", i, type_name(dev->properties[i].field.type));
    printf("]}\n");
    return 0;
}
