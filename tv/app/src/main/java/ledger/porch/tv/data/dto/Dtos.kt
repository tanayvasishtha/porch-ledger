package ledger.porch.tv.data.dto

import kotlinx.serialization.Serializable

@Serializable
data class VisitCard(
    val id: String,
    val kind: String,
    val startMs: Long,
    val endMs: Long,
    val title: String,
    val span: String,
    val facts: List<String> = emptyList(),
    val description: String = "",
    val heroUrl: String? = null,
    val clipUrl: String? = null,
    val recipientId: String? = null,
    val blocksDoor: Boolean? = null,
    val claimedBy: String? = null,
    val provenance: String = "",
    val version: Int = 1,
)

@Serializable
data class Folded(
    val carsPassed: Int = 0,
    val activity: Int = 0,
)

@Serializable
data class VisitList(
    val houseId: String,
    val day: String,
    val version: Int,
    val cards: List<VisitCard> = emptyList(),
    val folded: Folded = Folded(),
)

@Serializable
data class BoxOut(
    val x: Float,
    val y: Float,
    val w: Float,
    val h: Float,
    val recipientId: String? = null,
    val recipientState: String = "",
    val blocksDoor: Boolean = false,
)

@Serializable
data class ToolCallOut(
    val tool: String,
    val ok: Boolean,
    val latencyMs: Long = 0,
    val note: String = "",
)

@Serializable
data class VisitDetail(
    val id: String,
    val kind: String,
    val startMs: Long,
    val endMs: Long,
    val title: String,
    val span: String,
    val facts: List<String> = emptyList(),
    val description: String = "",
    val heroUrl: String? = null,
    val clipUrl: String? = null,
    val recipientId: String? = null,
    val blocksDoor: Boolean? = null,
    val claimedBy: String? = null,
    val provenance: String = "",
    val version: Int = 1,
    val box: BoxOut? = null,
    val doorOverlap: Float? = null,
    val trace: List<ToolCallOut> = emptyList(),
)

@Serializable
data class ResidentOut(
    val id: String,
    val displayName: String,
)

@Serializable
data class ClaimRequest(
    val residentId: String,
)

@Serializable
data class Problem(
    val type: String = "",
    val title: String = "",
    val status: Int = 0,
    val detail: String = "",
)
