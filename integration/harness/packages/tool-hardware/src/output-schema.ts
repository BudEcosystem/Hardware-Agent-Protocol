/** Generated projection of HMS local-api.schema.json; full bounds and semantics remain in the checked Python client. */
// Source SHA-256: bc24763b8209eb94d9a801d7a880bf3dbbf7f4ca24ac29dd322a8fac5895164e
import type { HardwareMethod } from '@budmh/experimental-hardware'
import type { ValueSchemaSpec } from '@budmh/tools'
const results = JSON.parse(String.raw`{
  "description": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "instance": {
        "type": "object",
        "additionalProperties": false,
        "properties": {
          "id": {
            "type": "string",
            "required": true
          },
          "deployment": {
            "type": "string",
            "required": true
          },
          "type_digest": {
            "type": "string",
            "required": true
          },
          "identity_kind": {
            "type": "string",
            "enum": [
              "simulation",
              "gateway",
              "device"
            ],
            "required": true
          },
          "identity_ref": {
            "type": "string",
            "required": true
          },
          "retired": {
            "type": "integer",
            "enum": [
              0,
              1
            ],
            "required": true
          }
        },
        "required": true
      },
      "descriptionDigest": {
        "type": "string",
        "required": true
      },
      "type": {
        "type": "object",
        "additionalProperties": false,
        "properties": {
          "profile": {
            "type": "string",
            "const": "hms.type-bundle/0.1",
            "required": true
          },
          "td": {
            "type": "object",
            "additionalProperties": true,
            "required": true
          },
          "execution": {
            "type": "object",
            "additionalProperties": false,
            "properties": {
              "profile": {
                "type": "string",
                "const": "hms.execution-contract/0.1",
                "required": true
              },
              "requiredFeatures": {
                "type": "array",
                "items": {
                  "type": "string",
                  "enum": [
                    "binding-generations/1",
                    "durable-operations/1",
                    "host-invoke/0.1",
                    "physical-evidence/1"
                  ]
                },
                "required": true
              },
              "capabilities": {
                "type": "array",
                "items": {
                  "type": "string"
                },
                "required": true
              },
              "properties": {
                "type": "object",
                "additionalProperties": true,
                "required": true
              },
              "actions": {
                "type": "object",
                "additionalProperties": true,
                "required": true
              }
            },
            "required": true
          }
        },
        "required": true
      },
      "binding": {
        "oneOf": [
          {
            "type": "object",
            "additionalProperties": false,
            "properties": {
              "profile": {
                "type": "string",
                "const": "hms.binding/0.1",
                "required": true
              },
              "instanceId": {
                "type": "string",
                "required": true
              },
              "generation": {
                "type": "string",
                "required": true
              },
              "typeDigest": {
                "type": "string",
                "required": true
              },
              "calibrationRevision": {
                "type": "string",
                "required": true
              },
              "controlGeneration": {
                "type": "string",
                "required": true
              },
              "mode": {
                "type": "string",
                "enum": [
                  "simulation",
                  "uncommissioned"
                ],
                "required": true
              },
              "adapterId": {
                "type": "string",
                "required": true
              },
              "resourceMap": {
                "type": "object",
                "additionalProperties": true,
                "required": true
              },
              "argumentSchemas": {
                "type": "object",
                "additionalProperties": true,
                "required": true
              }
            }
          },
          {
            "type": "null"
          }
        ],
        "required": true
      },
      "bindingActive": {
        "type": "boolean",
        "required": true
      },
      "presence": {
        "oneOf": [
          {
            "type": "object",
            "additionalProperties": false,
            "properties": {
              "session": {
                "type": "string",
                "required": true
              },
              "expires_ms": {
                "type": "integer",
                "required": true
              }
            }
          },
          {
            "type": "null"
          }
        ],
        "required": true
      },
      "registryRevision": {
        "type": "integer",
        "required": true
      }
    }
  },
  "discovery": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "items": {
        "type": "array",
        "items": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "instanceId": {
              "type": "string",
              "required": true
            },
            "descriptionDigest": {
              "type": "string",
              "required": true
            },
            "identityKind": {
              "type": "string",
              "enum": [
                "simulation",
                "gateway",
                "device"
              ],
              "required": true
            },
            "retired": {
              "type": "boolean",
              "required": true
            },
            "bindingGeneration": {
              "oneOf": [
                {
                  "type": "string"
                },
                {
                  "type": "null"
                }
              ],
              "required": true
            },
            "bindingActive": {
              "type": "boolean",
              "required": true
            },
            "presence": {
              "oneOf": [
                {
                  "type": "object",
                  "additionalProperties": false,
                  "properties": {
                    "session": {
                      "type": "string",
                      "required": true
                    },
                    "expires_ms": {
                      "type": "integer",
                      "required": true
                    }
                  }
                },
                {
                  "type": "null"
                }
              ],
              "required": true
            }
          }
        },
        "required": true
      },
      "cursor": {
        "oneOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "required": true
      },
      "registryRevision": {
        "type": "integer",
        "required": true
      }
    }
  },
  "events": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "events": {
        "type": "array",
        "items": {
          "oneOf": [
            {
              "type": "object",
              "additionalProperties": false,
              "properties": {
                "operation_id": {
                  "type": "string",
                  "required": true
                },
                "sequence": {
                  "type": "integer",
                  "required": true
                },
                "time_ms": {
                  "type": "integer",
                  "required": true
                },
                "clock_status": {
                  "type": "string",
                  "enum": [
                    "unqualified_host_clock",
                    "regressed_clamped",
                    "unavailable_clamped"
                  ],
                  "required": true
                },
                "kind": {
                  "type": "string",
                  "const": "accepted",
                  "required": true
                },
                "payload": {
                  "type": "object",
                  "additionalProperties": false,
                  "properties": {
                    "digest": {
                      "type": "string",
                      "required": true
                    }
                  },
                  "required": true
                }
              }
            },
            {
              "type": "object",
              "additionalProperties": false,
              "properties": {
                "operation_id": {
                  "type": "string",
                  "required": true
                },
                "sequence": {
                  "type": "integer",
                  "required": true
                },
                "time_ms": {
                  "type": "integer",
                  "required": true
                },
                "clock_status": {
                  "type": "string",
                  "enum": [
                    "unqualified_host_clock",
                    "regressed_clamped",
                    "unavailable_clamped"
                  ],
                  "required": true
                },
                "kind": {
                  "type": "string",
                  "const": "dispatch_claimed",
                  "required": true
                },
                "payload": {
                  "type": "object",
                  "additionalProperties": false,
                  "properties": {
                    "attemptId": {
                      "type": "string",
                      "required": true
                    },
                    "ownerEpoch": {
                      "type": "integer",
                      "required": true
                    }
                  },
                  "required": true
                }
              }
            },
            {
              "type": "object",
              "additionalProperties": false,
              "properties": {
                "operation_id": {
                  "type": "string",
                  "required": true
                },
                "sequence": {
                  "type": "integer",
                  "required": true
                },
                "time_ms": {
                  "type": "integer",
                  "required": true
                },
                "clock_status": {
                  "type": "string",
                  "enum": [
                    "unqualified_host_clock",
                    "regressed_clamped",
                    "unavailable_clamped"
                  ],
                  "required": true
                },
                "kind": {
                  "type": "string",
                  "const": "execution_evidence",
                  "required": true
                },
                "payload": {
                  "type": "object",
                  "additionalProperties": false,
                  "properties": {
                    "state": {
                      "type": "string",
                      "enum": [
                        "running",
                        "completed",
                        "failed",
                        "canceled"
                      ],
                      "required": true
                    },
                    "evidence": {
                      "type": "object",
                      "additionalProperties": false,
                      "properties": {
                        "kind": {
                          "type": "string",
                          "enum": [
                            "sensor",
                            "controller",
                            "simulation",
                            "runtime"
                          ],
                          "required": true
                        },
                        "source": {
                          "type": "string",
                          "required": true
                        },
                        "reference": {
                          "type": "string",
                          "required": true
                        },
                        "assertions": {
                          "type": "array",
                          "items": {
                            "type": "string",
                            "enum": [
                              "running",
                              "completed",
                              "failed",
                              "terminated",
                              "cancel_ack",
                              "resources_quiescent",
                              "physical_verified",
                              "verification_failed",
                              "disputed"
                            ]
                          },
                          "required": true
                        }
                      },
                      "required": true
                    }
                  },
                  "required": true
                }
              }
            },
            {
              "type": "object",
              "additionalProperties": false,
              "properties": {
                "operation_id": {
                  "type": "string",
                  "required": true
                },
                "sequence": {
                  "type": "integer",
                  "required": true
                },
                "time_ms": {
                  "type": "integer",
                  "required": true
                },
                "clock_status": {
                  "type": "string",
                  "enum": [
                    "unqualified_host_clock",
                    "regressed_clamped",
                    "unavailable_clamped"
                  ],
                  "required": true
                },
                "kind": {
                  "type": "string",
                  "const": "reconciled",
                  "required": true
                },
                "payload": {
                  "type": "object",
                  "additionalProperties": false,
                  "properties": {
                    "state": {
                      "type": "string",
                      "enum": [
                        "running",
                        "completed",
                        "failed",
                        "canceled"
                      ],
                      "required": true
                    },
                    "evidence": {
                      "type": "object",
                      "additionalProperties": false,
                      "properties": {
                        "kind": {
                          "type": "string",
                          "enum": [
                            "sensor",
                            "controller",
                            "simulation",
                            "runtime"
                          ],
                          "required": true
                        },
                        "source": {
                          "type": "string",
                          "required": true
                        },
                        "reference": {
                          "type": "string",
                          "required": true
                        },
                        "assertions": {
                          "type": "array",
                          "items": {
                            "type": "string",
                            "enum": [
                              "running",
                              "completed",
                              "failed",
                              "terminated",
                              "cancel_ack",
                              "resources_quiescent",
                              "physical_verified",
                              "verification_failed",
                              "disputed"
                            ]
                          },
                          "required": true
                        }
                      },
                      "required": true
                    }
                  },
                  "required": true
                }
              }
            },
            {
              "type": "object",
              "additionalProperties": false,
              "properties": {
                "operation_id": {
                  "type": "string",
                  "required": true
                },
                "sequence": {
                  "type": "integer",
                  "required": true
                },
                "time_ms": {
                  "type": "integer",
                  "required": true
                },
                "clock_status": {
                  "type": "string",
                  "enum": [
                    "unqualified_host_clock",
                    "regressed_clamped",
                    "unavailable_clamped"
                  ],
                  "required": true
                },
                "kind": {
                  "type": "string",
                  "const": "canceled_before_dispatch",
                  "required": true
                },
                "payload": {
                  "type": "object",
                  "additionalProperties": false,
                  "properties": {
                    "proof": {
                      "type": "string",
                      "const": "exclusive_accepted_state",
                      "required": true
                    }
                  },
                  "required": true
                }
              }
            },
            {
              "type": "object",
              "additionalProperties": false,
              "properties": {
                "operation_id": {
                  "type": "string",
                  "required": true
                },
                "sequence": {
                  "type": "integer",
                  "required": true
                },
                "time_ms": {
                  "type": "integer",
                  "required": true
                },
                "clock_status": {
                  "type": "string",
                  "enum": [
                    "unqualified_host_clock",
                    "regressed_clamped",
                    "unavailable_clamped"
                  ],
                  "required": true
                },
                "kind": {
                  "type": "string",
                  "const": "cancel_requested",
                  "required": true
                },
                "payload": {
                  "type": "object",
                  "additionalProperties": false,
                  "properties": {},
                  "required": true
                }
              }
            },
            {
              "type": "object",
              "additionalProperties": false,
              "properties": {
                "operation_id": {
                  "type": "string",
                  "required": true
                },
                "sequence": {
                  "type": "integer",
                  "required": true
                },
                "time_ms": {
                  "type": "integer",
                  "required": true
                },
                "clock_status": {
                  "type": "string",
                  "enum": [
                    "unqualified_host_clock",
                    "regressed_clamped",
                    "unavailable_clamped"
                  ],
                  "required": true
                },
                "kind": {
                  "type": "string",
                  "const": "cancel_ack",
                  "required": true
                },
                "payload": {
                  "type": "object",
                  "additionalProperties": false,
                  "properties": {
                    "accepted": {
                      "type": "boolean",
                      "required": true
                    },
                    "evidence": {
                      "type": "object",
                      "additionalProperties": false,
                      "properties": {
                        "kind": {
                          "type": "string",
                          "enum": [
                            "sensor",
                            "controller",
                            "simulation",
                            "runtime"
                          ],
                          "required": true
                        },
                        "source": {
                          "type": "string",
                          "required": true
                        },
                        "reference": {
                          "type": "string",
                          "required": true
                        },
                        "assertions": {
                          "type": "array",
                          "items": {
                            "type": "string",
                            "enum": [
                              "running",
                              "completed",
                              "failed",
                              "terminated",
                              "cancel_ack",
                              "resources_quiescent",
                              "physical_verified",
                              "verification_failed",
                              "disputed"
                            ]
                          },
                          "required": true
                        }
                      },
                      "required": true
                    }
                  },
                  "required": true
                }
              }
            },
            {
              "type": "object",
              "additionalProperties": false,
              "properties": {
                "operation_id": {
                  "type": "string",
                  "required": true
                },
                "sequence": {
                  "type": "integer",
                  "required": true
                },
                "time_ms": {
                  "type": "integer",
                  "required": true
                },
                "clock_status": {
                  "type": "string",
                  "enum": [
                    "unqualified_host_clock",
                    "regressed_clamped",
                    "unavailable_clamped"
                  ],
                  "required": true
                },
                "kind": {
                  "type": "string",
                  "const": "resources_released",
                  "required": true
                },
                "payload": {
                  "type": "object",
                  "additionalProperties": false,
                  "properties": {
                    "evidence": {
                      "type": "object",
                      "additionalProperties": false,
                      "properties": {
                        "kind": {
                          "type": "string",
                          "enum": [
                            "sensor",
                            "controller",
                            "simulation",
                            "runtime"
                          ],
                          "required": true
                        },
                        "source": {
                          "type": "string",
                          "required": true
                        },
                        "reference": {
                          "type": "string",
                          "required": true
                        },
                        "assertions": {
                          "type": "array",
                          "items": {
                            "type": "string",
                            "enum": [
                              "running",
                              "completed",
                              "failed",
                              "terminated",
                              "cancel_ack",
                              "resources_quiescent",
                              "physical_verified",
                              "verification_failed",
                              "disputed"
                            ]
                          },
                          "required": true
                        }
                      },
                      "required": true
                    }
                  },
                  "required": true
                }
              }
            },
            {
              "type": "object",
              "additionalProperties": false,
              "properties": {
                "operation_id": {
                  "type": "string",
                  "required": true
                },
                "sequence": {
                  "type": "integer",
                  "required": true
                },
                "time_ms": {
                  "type": "integer",
                  "required": true
                },
                "clock_status": {
                  "type": "string",
                  "enum": [
                    "unqualified_host_clock",
                    "regressed_clamped",
                    "unavailable_clamped"
                  ],
                  "required": true
                },
                "kind": {
                  "type": "string",
                  "const": "evidence_dispute",
                  "required": true
                },
                "payload": {
                  "type": "object",
                  "additionalProperties": false,
                  "properties": {
                    "evidence": {
                      "type": "object",
                      "additionalProperties": false,
                      "properties": {
                        "kind": {
                          "type": "string",
                          "enum": [
                            "sensor",
                            "controller",
                            "simulation",
                            "runtime"
                          ],
                          "required": true
                        },
                        "source": {
                          "type": "string",
                          "required": true
                        },
                        "reference": {
                          "type": "string",
                          "required": true
                        },
                        "assertions": {
                          "type": "array",
                          "items": {
                            "type": "string",
                            "enum": [
                              "running",
                              "completed",
                              "failed",
                              "terminated",
                              "cancel_ack",
                              "resources_quiescent",
                              "physical_verified",
                              "verification_failed",
                              "disputed"
                            ]
                          },
                          "required": true
                        }
                      },
                      "required": true
                    }
                  },
                  "required": true
                }
              }
            },
            {
              "type": "object",
              "additionalProperties": false,
              "properties": {
                "operation_id": {
                  "type": "string",
                  "required": true
                },
                "sequence": {
                  "type": "integer",
                  "required": true
                },
                "time_ms": {
                  "type": "integer",
                  "required": true
                },
                "clock_status": {
                  "type": "string",
                  "enum": [
                    "unqualified_host_clock",
                    "regressed_clamped",
                    "unavailable_clamped"
                  ],
                  "required": true
                },
                "kind": {
                  "type": "string",
                  "const": "recovery_unknown",
                  "required": true
                },
                "payload": {
                  "type": "object",
                  "additionalProperties": false,
                  "properties": {
                    "reason": {
                      "type": "string",
                      "required": true
                    }
                  },
                  "required": true
                }
              }
            },
            {
              "type": "object",
              "additionalProperties": false,
              "properties": {
                "operation_id": {
                  "type": "string",
                  "required": true
                },
                "sequence": {
                  "type": "integer",
                  "required": true
                },
                "time_ms": {
                  "type": "integer",
                  "required": true
                },
                "clock_status": {
                  "type": "string",
                  "enum": [
                    "unqualified_host_clock",
                    "regressed_clamped",
                    "unavailable_clamped"
                  ],
                  "required": true
                },
                "kind": {
                  "type": "string",
                  "const": "outcome_unknown",
                  "required": true
                },
                "payload": {
                  "type": "object",
                  "additionalProperties": false,
                  "properties": {
                    "reason": {
                      "type": "string",
                      "required": true
                    }
                  },
                  "required": true
                }
              }
            },
            {
              "type": "object",
              "additionalProperties": false,
              "properties": {
                "operation_id": {
                  "type": "string",
                  "required": true
                },
                "sequence": {
                  "type": "integer",
                  "required": true
                },
                "time_ms": {
                  "type": "integer",
                  "required": true
                },
                "clock_status": {
                  "type": "string",
                  "enum": [
                    "unqualified_host_clock",
                    "regressed_clamped",
                    "unavailable_clamped"
                  ],
                  "required": true
                },
                "kind": {
                  "type": "string",
                  "const": "rejected_before_dispatch",
                  "required": true
                },
                "payload": {
                  "type": "object",
                  "additionalProperties": false,
                  "properties": {
                    "reason": {
                      "type": "string",
                      "required": true
                    }
                  },
                  "required": true
                }
              }
            }
          ]
        },
        "required": true
      },
      "next": {
        "type": "integer",
        "required": true
      },
      "head": {
        "type": "integer",
        "required": true
      },
      "gap": {
        "type": "boolean",
        "const": false,
        "required": true
      }
    }
  },
  "namespace": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "token": {
        "type": "string",
        "required": true
      },
      "epoch": {
        "type": "integer",
        "required": true
      },
      "expiresUnixMs": {
        "type": "integer",
        "required": true
      },
      "authorityId": {
        "type": "string",
        "required": true
      }
    }
  },
  "observation": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "protocol": {
        "type": "string",
        "const": "hms.observation/0.1",
        "required": true
      },
      "instanceId": {
        "type": "string",
        "required": true
      },
      "propertyId": {
        "type": "string",
        "required": true
      },
      "value": {
        "type": "json",
        "required": true
      },
      "unit": {
        "type": "string",
        "required": true
      },
      "frame": {
        "oneOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "required": true
      },
      "evidenceKind": {
        "type": "string",
        "enum": [
          "physical_sensor",
          "controller_measurement",
          "command_echo",
          "estimate",
          "simulation"
        ],
        "required": true
      },
      "source": {
        "type": "string",
        "required": true
      },
      "quality": {
        "type": "string",
        "enum": [
          "valid",
          "stale",
          "invalid",
          "unknown"
        ],
        "required": true
      },
      "streamEpoch": {
        "type": "string",
        "required": true
      },
      "sequence": {
        "type": "integer",
        "required": true
      },
      "endpointSession": {
        "type": "string",
        "required": true
      },
      "controlGeneration": {
        "type": "string",
        "required": true
      },
      "bindingGeneration": {
        "type": "string",
        "required": true
      },
      "calibrationRevision": {
        "type": "string",
        "required": true
      },
      "acquisition": {
        "type": "object",
        "additionalProperties": false,
        "properties": {
          "clockDomain": {
            "type": "string",
            "required": true
          },
          "clockEpoch": {
            "type": "string",
            "required": true
          },
          "ticksMs": {
            "type": "integer",
            "required": true
          }
        },
        "required": true
      },
      "receipt": {
        "type": "object",
        "additionalProperties": false,
        "properties": {
          "clockDomain": {
            "type": "string",
            "required": true
          },
          "clockEpoch": {
            "type": "string",
            "required": true
          },
          "ticksMs": {
            "type": "integer",
            "required": true
          }
        },
        "required": true
      },
      "acquisitionLatencyBoundMs": {
        "oneOf": [
          {
            "type": "integer"
          },
          {
            "type": "null"
          }
        ],
        "required": true
      },
      "clockUncertaintyMs": {
        "oneOf": [
          {
            "type": "integer"
          },
          {
            "type": "null"
          }
        ],
        "required": true
      },
      "measurementUncertainty": {
        "oneOf": [
          {
            "type": "object",
            "additionalProperties": false,
            "properties": {
              "absolute": {
                "type": "number",
                "required": true
              },
              "unit": {
                "type": "string",
                "required": true
              },
              "method": {
                "type": "string",
                "required": true
              }
            }
          },
          {
            "type": "null"
          }
        ],
        "required": true
      },
      "ageUpperBoundMs": {
        "oneOf": [
          {
            "type": "integer"
          },
          {
            "type": "null"
          }
        ],
        "required": true
      }
    }
  },
  "operation": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "protocol": {
        "type": "string",
        "const": "hms.operation/0.1",
        "required": true
      },
      "operationId": {
        "type": "string",
        "required": true
      },
      "requestDigest": {
        "type": "string",
        "required": true
      },
      "instanceId": {
        "type": "string",
        "required": true
      },
      "actionId": {
        "type": "string",
        "required": true
      },
      "executionState": {
        "type": "string",
        "enum": [
          "accepted",
          "dispatching",
          "running",
          "outcome_unknown",
          "completed",
          "failed",
          "canceled",
          "rejected_before_dispatch"
        ],
        "required": true
      },
      "cancellationState": {
        "type": "string",
        "enum": [
          "not_requested",
          "requested",
          "acknowledged",
          "rejected",
          "confirmed"
        ],
        "required": true
      },
      "effectVerification": {
        "type": "string",
        "enum": [
          "unverified",
          "verified",
          "failed"
        ],
        "required": true
      },
      "mayHaveActed": {
        "type": "boolean",
        "required": true
      },
      "eventSequence": {
        "type": "integer",
        "required": true
      },
      "resourceClaims": {
        "type": "array",
        "items": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "resource": {
              "type": "string",
              "required": true
            },
            "fence": {
              "type": "integer",
              "required": true
            }
          }
        },
        "required": true
      },
      "result": {
        "oneOf": [
          {
            "type": "object",
            "additionalProperties": false,
            "properties": {
              "evidenceKind": {
                "type": "string",
                "enum": [
                  "sensor",
                  "controller",
                  "simulation"
                ],
                "required": true
              },
              "output": {
                "type": "object",
                "additionalProperties": true,
                "required": true
              }
            }
          },
          {
            "type": "null"
          }
        ],
        "required": true
      }
    }
  },
  "prepared": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "request": {
        "type": "object",
        "additionalProperties": false,
        "properties": {
          "protocol": {
            "type": "string",
            "const": "hms.invoke/0.1",
            "required": true
          },
          "replayNamespace": {
            "type": "string",
            "required": true
          },
          "operationKey": {
            "type": "string",
            "required": true
          },
          "intent": {
            "type": "object",
            "additionalProperties": false,
            "properties": {
              "instanceId": {
                "type": "string",
                "required": true
              },
              "endpointSession": {
                "type": "string",
                "required": true
              },
              "controlGeneration": {
                "type": "string",
                "required": true
              },
              "actionId": {
                "type": "string",
                "required": true
              },
              "descriptionDigest": {
                "type": "string",
                "required": true
              },
              "bindingGeneration": {
                "type": "string",
                "required": true
              },
              "calibrationRevision": {
                "type": "string",
                "required": true
              },
              "arguments": {
                "type": "object",
                "additionalProperties": true,
                "required": true
              },
              "requiredEffect": {
                "type": "string",
                "enum": [
                  "capability_completion",
                  "physical_verified"
                ],
                "required": true
              },
              "timing": {
                "type": "object",
                "additionalProperties": false,
                "properties": {
                  "notBeforeUnixMs": {
                    "type": "integer",
                    "required": true
                  },
                  "latestStartUnixMs": {
                    "type": "integer",
                    "required": true
                  },
                  "latestCompletionUnixMs": {
                    "type": "integer",
                    "required": true
                  },
                  "maxRunMs": {
                    "type": "integer",
                    "required": true
                  }
                },
                "required": true
              }
            },
            "required": true
          }
        },
        "required": true
      },
      "requestDigest": {
        "type": "string",
        "required": true
      },
      "admitted": {
        "type": "boolean",
        "const": false,
        "required": true
      }
    }
  }
}`) as Record<string, ValueSchemaSpec>
const methods = JSON.parse(String.raw`{
  "discover": "discovery",
  "describe": "description",
  "observe": "observation",
  "namespace": "namespace",
  "prepare": "prepared",
  "invoke": "operation",
  "operation": "operation",
  "cancel": "operation",
  "events": "events"
}`) as Record<HardwareMethod, string>
const attribution: ValueSchemaSpec = { type: 'object', additionalProperties: false, properties: {
  sessionId: { oneOf: [{ type: 'string' }, { type: 'null' }], required: true }, callId: { type: 'string', required: true },
} }
/** Closed carrier with method-specific identity, state, and evidence fields. */
export function hardwareOutputSchema(method: HardwareMethod): ValueSchemaSpec {
  const result = results[methods[method]]
  if (result === undefined) throw new Error('hardware output schema missing')
  return { oneOf: [
    { type: 'object', additionalProperties: false, properties: {
      ok: { type: 'boolean', const: true, required: true }, result: { ...result, required: true }, attribution: { ...attribution, required: true },
    } },
    { type: 'object', additionalProperties: false, properties: {
      ok: { type: 'boolean', const: false, required: true }, outcome: { type: 'string', const: 'unconfirmed', required: true },
      error: { type: 'object', additionalProperties: false, required: true, properties: { code: { type: 'string', required: true } } }, attribution: { ...attribution, required: true },
    } },
  ] }
}
