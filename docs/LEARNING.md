# Learning, rewards and memory

## Intended experiment

The aim is to investigate whether sensory-driven neural activity, an adaptive artificial body and outcome-contingent reinforcement can produce more useful billiards actions over repeated play. “Can learn” is a hypothesis and an implemented adaptation mechanism, not an established result.

The fly is assigned stripes and the human solids. That rule lives in the environment's reward evaluator. It is not provided to the neural controller as a symbolic label. For the controller to improve, its neural features and learned action mapping would have to develop useful associations between the table image, its cue action and the later reward.

## Native neural plasticity

`flyblox/brain/plasticity.py` wraps the pinned upstream `stonkfly.neural.rule.advance` implementation. Neural activity drives KC and dopamine-neuron traces; the selected circuit and learning rate determine changes to 7,835 KC→MBON edges. The runtime applies the resulting multiplicative factors to their baseline weights.

This is the installed model's specific plasticity approximation. It is not an implementation of every learning rule found in a fly, and it does not train every edge in the full graph. The current model selects 15 PAM11 neurons for artificial reward injection. The full graph can also generate endogenous modulation; a zero game reward means **no new artificial reward pulse**, not that all dopamine-related activity is zero.

## Artificial cue readout

Population spike rates are exponentially smoothed with a 0.2-neural-second time constant and transformed by `tanh(rate / 100)`. The 43 channels plus a bias form a feature vector `f` of length 44. Two rows of weights produce `mu = W @ f`.

During learning, Gaussian exploration uses standard deviations `[1.5, 0.85]`. In evaluation mode these decrease to `[0.12, 0.10]`; evaluation is still stochastic rather than exactly deterministic. Angle wraps over a full turn. The second latent value is passed through a sigmoid and mapped to cue power between 0.08 and 1.

The sampled feature vector, exploration noise and scale are stored with the pending action. After the shot, the update is proportional to:

```text
advantage = clip(reward / 10 - baseline, -1, 2)
gradient = outer(noise / sigma, features)
gradient *= 0.018 * advantage / max(1, norm(features))
weights = clip(weights + gradient, -4, 4)
baseline = 0.95 * baseline + 0.05 * (reward / 10)
```

This is a small policy-gradient-style controller, not a biologically identified fly muscle circuit. It provides an artificial way to associate neural state with rewarded cue actions. It does not calculate an optimal shot using ball geometry. A zero-reward shot can produce a negative **relative** update when the reward baseline is positive; that comparison is not a dopamine punishment pulse.

## Reward categories and timing

The application evaluates only completed shots. Correct legal pots earn +10 per own ball, a legitimate winning black earns +10, a qualifying new approach earns +2, and an eligible first contact with a stripe earns +0.5. Wrong-group first contact, scratches and losing on the black suppress reward. See the exact rules and exceptions in the [README](../README.md#rewards-why-pocketing-the-right-ball-matters) and `biliardo/game.py`.

The high, medium and contact categories schedule 2,000, 350 and 120 neural ms respectively at the same artificial current amplitude of 20. Overlapping rewards extend the pending pulse deadline using a maximum; they do not add infinite amplitude. Multiple correct balls increase the scalar body reward, while the pulse remains in the high duration category.

The approach reward uses both the shot's initial distance and the historical best for each own ball, so oscillating around a previously reached position cannot repeatedly farm the medium reward. The contact reward deliberately makes reinforcement less sparse and can still reward many unproductive touches. That tradeoff is part of the experimental setup.

## What “memory” means here

A saved memory is explicit numerical state: learned synaptic/readout weights, eligibility/activity traces, voltages, delayed events, random state and the environment. It is not a text diary of concepts, a language model memory or evidence that the program consciously recalls a game.

Creating a new table preserves this learned state. Starting from a clean checkout starts a new experiment. The developer's original live sessions are not bundled as a pretrained policy. Old memories only load if their graph, model sources, configuration and save version remain compatible.

Turning learning off freezes native weights and learning traces, freezes the readout updates and clears/disables artificial reward pulses. The visual neural dynamics still run and actions can still occur. Leaving the game idle may still advance active neural dynamics, but it does not create the varied action/outcome experience needed to test task learning.

## Why more dopamine is not enough

- The retinal features are heavily pooled. Useful ball identity, relative location and pocket geometry may not be adequately represented in the readout.
- The action space covers a full circle and a continuous power range; exploration is broad.
- A successful pocket is sparse and can be accidental. Intermediate contact rewards help frequency but may favor merely touching balls.
- Neural and real time differ, and reinforcement arrives after a whole shot rather than instantaneously with a particular motor spike.
- Plasticity can change a model without improving the chosen task. It can also preserve or amplify unhelpful behavior.

Reliable progress must be demonstrated through frozen-policy evaluations on many comparable table states, against baselines, with repeated seeds and clear outcome metrics. Increasing reward magnitude, showing active neurons or observing one successful pot is not a substitute. The suggested protocol is in [VALIDATION.md](VALIDATION.md).
