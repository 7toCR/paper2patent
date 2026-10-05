# Patentability and Disclosure

Read this at intake, every time. It decides what you must tell the user before or alongside the draft. You are not giving legal advice; you are flagging risks a patent attorney will confirm.

Legal basis current as of the 2020 Patent Law, the 2023 Implementing Regulations (effective 2024-01-20) and the 专利审查指南 as amended by CNIPA Order No. 84 (effective 2026-01-01). If the user's situation depends on a detail not covered here, say so and recommend an attorney.

## Contents

1. Disclosure and novelty (the paper itself may be prior art)
2. Grace period (专利法第24条)
3. Technical character of AI / algorithm inventions (专利法第25条, 审查指南第二部分第九章第6节)
4. Sufficiency and inventive step for AI inventions (2026 rules)
5. Data and ethics (专利法第5条)
6. What to write in the drafting notes

## 1. Disclosure and novelty

专利法第22条: an invention must be new, inventive and practically applicable; 现有技术 means "申请日以前在国内外为公众所知的技术". If the paper was public before the filing date, everything it discloses is prior art against the application — including against claims drafted from it.

Events that make the paper (or its content) public:

- arXiv / SSRN / TechRxiv or any preprint server, including earlier versions;
- online-first or proceedings publication (IEEE Xplore, ACM DL, Springer, journal websites);
- open-review platforms that show submissions publicly (e.g. OpenReview for ICLR) — public at posting time, even before acceptance;
- conference talk, poster, demo, recorded video, slides posted online;
- public code, model weights, project page, blog, social-media thread, press release;
- a thesis available in a library or database.

Usually *not* public: a double-blind submission under confidential review, a private preprint shared under confidentiality.

Other jurisdictions differ (e.g. the US has a one-year grace period for the inventor's own disclosure; the EPO essentially has none for publications). If the user mentions foreign filing or PCT, flag that the strictest jurisdiction governs the timing.

## 2. Grace period (专利法第24条)

Within six months before the filing date, a disclosure does not destroy novelty only in four cases:

1. 在国家出现紧急状态或者非常情况时，为公共利益目的首次公开的；
2. 在中国政府主办或者承认的国际展览会上首次展出的；
3. 在规定的学术会议或者技术会议上首次发表的；
4. 他人未经申请人同意而泄露其内容的。

实施细则第33条 defines case 3 as "国务院有关主管部门或者全国性学术团体组织召开的学术会议或者技术会议，以及国务院有关主管部门认可的由国际组织召开的学术会议或者技术会议". Do not assume that a typical international venue (CVPR, NeurIPS, ICASSP, ACL …) qualifies; arXiv never does. Cases 2 and 3 require a declaration at filing and proof within two months of the filing date. The grace period is not a priority right: a third party's independent disclosure in the meantime still counts as prior art, and a further disclosure by the applicant that is not itself one of the four cases destroys novelty.

## Decision table

| Disclosure status | What to do |
|---|---|
| Not yet public | Proceed. Tell the user to file before any public disclosure — arXiv, camera-ready publication, code release, talk. |
| Public, < 6 months, plausibly one of the four cases | Proceed. Note the declaration and two-month proof requirement and that qualification must be confirmed. |
| Public and not a grace-period case, or > 6 months | Still draft if the user wants it, but say clearly, before the files, that the paper is prior art: claims built only from what the paper discloses are very likely to lack novelty. Patentability would have to rest on unpublished improvements or implementation details, which only the user can supply — ask for them; never invent them. |
| Unknown | `human-in-loop`: ask. `direct`: proceed, infer what you can from the material (arXiv ID, "Published in", DOI, venue and year on the PDF), and list the question as the first item in the drafting notes. |

## 3. Technical character (专利法第25条)

"智力活动的规则和方法" are excluded. 审查指南第二部分第九章第6节 (title since 2026: 涉及人工智能、大数据等包含算法特征或商业规则和方法特征的发明) requires the claim to be assessed as a whole — technical features and algorithm features are not split apart — and asks whether it uses technical means to solve a technical problem and achieve a technical effect.

Framings that usually pass:

- The algorithm processes data with a definite technical meaning in a specific technical field (image pixels, audio waveforms, sensor signals, network traffic, medical images, power-grid measurements), and solves a technical problem there.
- The algorithm has a specific technical relationship with the computer's internal structure and improves its performance (memory, computation, bandwidth, latency).
- Big-data processing that mines relationships following natural laws to solve a technical problem (e.g. improving reliability or precision of an analysis).

Framings that usually fail:

- A model or training procedure described only abstractly ("输入数据" → "输出结果") with no technical meaning attached to the data.
- Rules following economic, social or business laws (the guidelines' example: predicting financial product prices with a neural network fails because prices follow economic, not natural, laws).

Drafting consequences: name the technical field in 技术领域 and claim 1's subject; name the data concretely (视频帧、梅尔频谱、点云) rather than "数据"; state the technical problem and effect in technical terms (误检率、延迟、显存占用、信噪比), using the paper's own measurements.

## 4. Sufficiency and inventive step for AI inventions (2026 rules)

- Model construction or training: the description must clearly record the model's necessary modules, layers or connection relations, and the specific steps and parameters required for training.
- Application of a model or algorithm in a field or scene: the description must clearly record how the model or algorithm is combined with that field or scene and how its input and output data are set. The guidelines' example of a cancer-prediction method failed sufficiency because the input-output relationship was unclear.
- Features that do not contribute to solving the technical problem normally do not support inventive step; features that do contribute (e.g. ones producing unexpected effects) must be written into the claims to be counted.
- Moving the same algorithm to a different scene, without algorithmic adaptation, tends to lack inventive step; substantive adaptations of the algorithm to the scene can support it. So claim 1 should contain the paper's actual adaptation, not just "apply model X to task Y".

Claim categories confirmed for computer-implemented solutions: method, apparatus (program-module architecture), computer-readable storage medium, computer program product; an electronic-device claim (processor + memory) is standard practice.

## 5. Data and ethics (专利法第5条)

Since 2026 the guidelines state that a solution whose data collection, labelling, rule setting or recommendation decisions violate law, social morality or public interest is not patentable. Examples given: face recognition in public places for marketing without consent (conflicts with the 个人信息保护法); algorithmic decisions that discriminate by gender or age.

If the paper uses personal, biometric or medical data, or makes decisions about people, record in the drafting notes how the paper says the data were obtained (consent, public dataset, anonymisation). Do not insert compliance statements the paper does not support; flag the gap for the user instead.

## 6. Drafting notes

Put this in `notes` (rendered into the 撰写说明 file, never into the application):

- `disclosure_status`: what you found and what it means (one short paragraph).
- `risks`: novelty/disclosure risk; subject-matter (客体) risk and how the draft addresses it; ethics/data issues; claim-scope concerns.
- `patentability`: one or two sentences on how the claims establish technical character.
- `handover`: what the applicant must still supply (rendered first in the 撰写说明, together with every `gaps` entry and the standard ownership / disclosure / search items).
- `next_steps`: e.g. prior-art search by the attorney, supply the missing material, decide on foreign filing before publication, and confirm the applicant and inventors (work done at a university or company is usually a 职务发明, so the employer is normally the applicant).
